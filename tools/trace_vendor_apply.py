"""Trace the original Apply handler in Unicorn; never opens a HID device.

This is a synthetic configuration, not a capture from a running vendor app.
Only the known Apply range and intercepted read/write/Sleep calls are allowed.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP
from verify_vendor import KNOWN_SHA256


def trace(executable, keys_mode=1, flags=0xC0, macro=None, state=None):
    if hashlib.sha256(executable).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown vendor executable')
    pe = pefile.PE(data=executable, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.mem_map(0x2000000, 0x40000)
    vm.reg_write(UC_X86_REG_ESP, 0x1001000)
    vm.reg_write(UC_X86_REG_EBP, 0x1010000)
    vm.mem_write(0x5BE478, struct.pack('<I', 0x2000100))
    vm.mem_write(0x624EF0, struct.pack('<H', 8))
    for address, value in ((0x625160, 1), (0x63DDA8, 0),
                           (0x61F104, keys_mode), (0x62527C, 0)):
        vm.mem_write(address, struct.pack('<I', value))
    vm.mem_write(0x63D9B0, b'\x02\x03')
    if macro is not None:
        if len(macro) != 0xB92:
            raise ValueError('Expected original internal macro structure')
        vm.mem_write(0x62527C, struct.pack('<I', 1))
        vm.mem_write(0x624E48, struct.pack('<I', 8192))
        vm.mem_write(0x61F038, bytes(4))
        vm.mem_write(0x61F088, bytes(4))
    for address, value in (state or {}).items():
        if not 0x61F000 <= address <= 0x648000:
            raise ValueError('Synthetic state address outside known globals')
        vm.mem_write(address, struct.pack('<I', value))
    events = []
    heap = 0x2004000

    def ret(arguments, value=1):
        sp = vm.reg_read(UC_X86_REG_ESP)
        target = struct.unpack('<I', vm.mem_read(sp, 4))[0]
        vm.reg_write(UC_X86_REG_ESP, sp + 4 + arguments)
        vm.reg_write(UC_X86_REG_EIP, target)
        vm.reg_write(UC_X86_REG_EAX, value)

    def hook(uc, ip, size, user):
        nonlocal heap
        if ip == 0x412528:
            uc.emu_stop()
        elif ip == 0x2000100:
            sp = uc.reg_read(UC_X86_REG_ESP)
            events.append({'sleep_ms': struct.unpack('<I', uc.mem_read(sp+4, 4))[0]})
            ret(4)
        elif ip == 0x40AC70 and macro is not None:
            sp = uc.reg_read(UC_X86_REG_ESP)
            buffer = struct.unpack('<I', uc.mem_read(sp+4, 4))[0]
            uc.mem_write(buffer, macro)
            ret(12, buffer)
        elif ip == 0x44800E:
            sp = uc.reg_read(UC_X86_REG_ESP)
            length = struct.unpack('<I', uc.mem_read(sp+4, 4))[0]
            target = heap
            heap += (length+15)&~15
            if heap > 0x2040000:
                raise RuntimeError('Synthetic heap exceeded')
            ret(0, target)
        elif ip == 0x590300:
            sp = uc.reg_read(UC_X86_REG_ESP)
            _, buffer, value, length = struct.unpack('<4I', uc.mem_read(sp, 16))
            uc.mem_write(buffer, bytes([value&255])*length)
            ret(0, buffer)
        elif ip == 0x58DD78:
            sp = uc.reg_read(UC_X86_REG_ESP)
            # free(), cdecl: the caller owns stack cleanup.
            ret(0)
        elif ip in (0x58F379, 0x58F373, 0x4071D0, 0x406FD0):
            sp = uc.reg_read(UC_X86_REG_ESP)
            _, a, buffer, length = struct.unpack('<4I', uc.mem_read(sp, 16))
            if ip == 0x58F379:
                events.append({'set': bytes(uc.mem_read(buffer, length)).hex()})
            elif ip == 0x58F373:
                if length != 16:
                    raise RuntimeError(f'Unexpected feature length {length}')
                uc.mem_write(buffer, bytes.fromhex('0700414043010201010264022801e000'))
                events.append({'get': length})
            elif ip == 0x4071D0:
                events.append({'write_address': a, 'data': bytes(uc.mem_read(buffer, length)).hex()})
            else:
                if a != 0xE0 or length != 1:
                    raise RuntimeError(f'Unexpected read {a:x}/{length}')
                uc.mem_write(buffer, bytes([flags]))
                events.append({'read_address': a, 'length': length})
            ret(12)
        elif not 0x410239 <= ip < 0x412528:
            raise RuntimeError(f'Unexpected code target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x410239, 0x412529, count=200000)
    if vm.reg_read(UC_X86_REG_EIP) != 0x412528:
        raise RuntimeError('Apply trace did not reach finalization')
    return events


if __name__ == '__main__':
    executable = Path(sys.argv[1]).read_bytes()
    result = json.dumps({'source_sha256': KNOWN_SHA256,
                         'synthetic_apply': trace(executable),
                         'keys_mode_zero': trace(executable, keys_mode=0)}, indent=2) + '\n'
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(result, encoding='utf8')
    else:
        print(result, end='')
