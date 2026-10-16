"""Bounded emulation of the vendor collection-open decision. No USB or OS I/O.

Usage: uv run --group research python tools/verify_vendor_connection.py APP.exe
All CreateFile calls return synthetic handles. Unknown calls/branches fail.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_ESP,
                              UC_X86_REG_EIP, UC_X86_REG_ECX)

from verify_vendor import KNOWN_SHA256


def decision(executable, page, usage=1, input_handle=-1, feature_handle=-1, open_ok=True):
    pe = pefile.PE(data=executable, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_EBP, 0x1011000)
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    def put(address, value):
        vm.mem_write(address, struct.pack('<I', value & 0xFFFFFFFF))
    put(0x61F034, input_handle)
    put(0x61F030, feature_handle)
    put(0x624F28, 0x1001000)
    vm.mem_write(0x1001004, 'synthetic-device\0'.encode('utf-16le'))
    vm.mem_write(0x624E68, struct.pack('<5H', usage, page, 3 if page == 0xFF00 else 0,
                                     0, 8 if page == 0xFF01 else 0) + bytes(54))
    put(0x5BE44C, 0x1000100)
    calls = []
    reads = []
    stop = None

    def hook(uc, ip, size, user):
        nonlocal stop
        if ip in (0x407A38, 0x407A87):
            stop = 'connected' if ip == 0x407A87 else 'continue-enumeration'
            uc.emu_stop()
        elif ip == 0x1000100:
            sp = uc.reg_read(UC_X86_REG_ESP)
            target, path, access, share, security, disposition, flags, template = struct.unpack(
                '<8I', uc.mem_read(sp, 32))
            calls.append(dict(api='CreateFileW', access=hex(access), share=share,
                              disposition=disposition, flags=flags,
                              security=security, template=template))
            uc.reg_write(UC_X86_REG_EAX, 0x12345678 if open_ok else 0xFFFFFFFF)
            uc.reg_write(UC_X86_REG_ESP, sp + 32)
            uc.reg_write(UC_X86_REG_EIP, target)
        elif not 0x407917 <= ip < 0x407A38:
            raise RuntimeError(f'Unexpected execution target {ip:x}')

    def read_hook(uc, kind, address, size, value, user):
        reads.append(dict(instruction=hex(uc.reg_read(UC_X86_REG_EIP)),
                          address=hex(address), size=size))

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.hook_add(UC_HOOK_MEM_READ, read_hook, begin=0x61F034, end=0x61F037)
    vm.emu_start(0x407917, 0x407A88, count=300)
    if stop is None:
        raise RuntimeError('Decision did not reach a bounded exit')
    return dict(page=hex(page), usage=usage, previous_input_handle=input_handle,
                previous_feature_handle=feature_handle, open_ok=open_ok,
                calls=calls, input_handle_reads=reads, outcome=stop)


def main():
    executable = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(executable).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown binary')
    cases = [decision(executable, 0xFF00),
             decision(executable, 0xFF01),
             decision(executable, 0xFF01, input_handle=0x12340000),
             decision(executable, 0xFF00, feature_handle=0x12340000),
             decision(executable, 0xFF00, usage=2),
             decision(executable, 0xFF01, input_handle=0x12340000, open_ok=False)]
    expected = ['continue-enumeration', 'continue-enumeration', 'connected',
                'connected', 'continue-enumeration', 'continue-enumeration']
    if [case['outcome'] for case in cases] != expected:
        raise RuntimeError('Unexpected connection decisions')
    if any(read['instruction'] != '0x407a0b' for case in cases for read in case['input_handle_reads']):
        raise RuntimeError('Unexpected use of FF00 handle')
    capture = keyboard_capture(executable)
    if capture['feature_reports'] != ['0709400000000000'] or capture['hooks'] != [13]:
        raise RuntimeError('Unexpected keyboard capture initialization')
    startup = startup_reports(executable)
    if startup != ['0718110000000000', '0718000000000000']:
        raise RuntimeError('Unexpected post-connect startup reports')
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, cases=cases,
                          keyboard_capture=capture, startup_reports=startup), indent=2))


def keyboard_capture(executable):
    """Trace the original key-assignment capture button through hook creation."""
    pe = pefile.PE(data=executable, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    vm.reg_write(UC_X86_REG_ECX, 13)
    vm.mem_write(0x624EF0, struct.pack('<H', 8))
    vm.mem_write(0x624F30, bytes(8))
    vm.mem_write(0x648FE4, bytes(4))
    vm.mem_write(0x61F030, struct.pack('<I', 0x12340000))
    vm.mem_write(0x5BE464, struct.pack('<I', 0x1000100))
    vm.mem_write(0x5BE7B4, struct.pack('<I', 0x1000200))
    reports = []
    hooks = []

    def ret(count, result=1):
        sp = vm.reg_read(UC_X86_REG_ESP)
        target = struct.unpack('<I', vm.mem_read(sp, 4))[0]
        vm.reg_write(UC_X86_REG_ESP, sp + 4 + count)
        vm.reg_write(UC_X86_REG_EAX, result)
        vm.reg_write(UC_X86_REG_EIP, target)

    def hook(uc, ip, size, user):
        if ip == 0x4284F1:
            uc.emu_stop()
        elif ip == 0x58F379:
            sp = uc.reg_read(UC_X86_REG_ESP)
            _, handle, buffer, length = struct.unpack('<4I', uc.mem_read(sp, 16))
            if handle != 0x12340000 or length != 8:
                raise RuntimeError('Unexpected capture report destination')
            reports.append(bytes(uc.mem_read(buffer, length)).hex())
            ret(12)
        elif ip == 0x1000100:
            ret(4)
        elif ip == 0x1000200:
            sp = uc.reg_read(UC_X86_REG_ESP)
            _, kind, callback, module, thread = struct.unpack('<5I', uc.mem_read(sp, 20))
            if callback != 0x427230 or thread != 0:
                raise RuntimeError('Unexpected hook callback')
            hooks.append(kind)
            ret(16)
        elif not 0x42849F <= ip < 0x4284F1:
            raise RuntimeError(f'Unexpected capture target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x42849F, 0x4284F2, count=100)
    if vm.reg_read(UC_X86_REG_EIP) != 0x4284F1:
        raise RuntimeError('Capture emulation did not reach bounded exit')
    return dict(feature_reports=reports, hooks=hooks, callback='0x427230')


def startup_reports(executable):
    """Trace the non-alternate-model post-connect initialization commands."""
    pe = pefile.PE(data=executable, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    vm.reg_write(UC_X86_REG_EBP, 0x1011000)
    vm.mem_write(0x63DDA8, bytes(4))
    vm.mem_write(0x624F30, bytes(8))
    vm.mem_write(0x624EF0, struct.pack('<H', 8))
    vm.mem_write(0x61F030, struct.pack('<I', 0x12340000))
    vm.mem_write(0x5BE478, struct.pack('<I', 0x1000100))
    reports = []

    def hook(uc, ip, size, user):
        if ip == 0x414B80:
            uc.emu_stop()
        elif ip in (0x58F379, 0x1000100):
            sp = uc.reg_read(UC_X86_REG_ESP)
            target = struct.unpack('<I', uc.mem_read(sp, 4))[0]
            if ip == 0x58F379:
                handle, buffer, length = struct.unpack('<3I', uc.mem_read(sp+4, 12))
                if handle != 0x12340000 or length != 8:
                    raise RuntimeError('Unexpected startup report destination')
                reports.append(bytes(uc.mem_read(buffer, length)).hex())
            uc.reg_write(UC_X86_REG_ESP, sp + (16 if ip == 0x58F379 else 8))
            uc.reg_write(UC_X86_REG_EIP, target)
            uc.reg_write(UC_X86_REG_EAX, 1)
        elif not (0x414B2D <= ip < 0x414B80 or 0x413030 <= ip <= 0x4130BA):
            raise RuntimeError(f'Unexpected startup target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x414B2D, 0x414B81, count=500)
    if vm.reg_read(UC_X86_REG_EIP) != 0x414B80:
        raise RuntimeError('Startup emulation did not reach bounded exit')
    return reports


if __name__ == '__main__':
    main()
