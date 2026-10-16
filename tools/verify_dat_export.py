"""Trace native single-macro DAT export values, replacing CString/file I/O.

The byte-selection code is original x86. Synthetic CString storage only keeps
control flow alive; decimal formatting and file writes are intercepted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP,
                              UC_X86_REG_EIP)
from verify_vendor import KNOWN_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--fixture', choices=('pattern', 'keyboard'), default='pattern')
    args = parser.parse_args()
    source = args.executable.read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0, 0x1000)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x80000)
    def put(address, value):
        vm.mem_write(address, struct.pack('<I', value))
    put(0x1001000, 0x1001100)
    put(0x100110C, 0x1000200)
    vm.mem_write(0x1004000, struct.pack('<4I', 0, 0, 100000, 1000000)+bytes(512))
    put(0x5BE458, 0x1000300)
    put(0x63DDfc, 1)
    put(0x63B978, 1)
    raw = bytes((i*13+7)&255 for i in range(0xB92))
    if args.fixture == 'keyboard':
        fixture = bytearray(0xB92)
        name = 'K810 roundtrip'.encode('utf-16le')
        fixture[:len(name)] = name
        struct.pack_into('<HH', fixture, 0x3E, 3, 4)
        for i, (kind, code, delay) in enumerate(((0, 4, 50), (1, 4, 250),
                                                (0, 0xE0, 10), (1, 0xE0, 20))):
            fixture[0x52+i] = kind
            fixture[0x165+i] = code
            struct.pack_into('<H', fixture, 0x6C4+i*2, delay)
        raw = bytes(fixture)
    vm.mem_write(0x63DE08, raw)
    vm.mem_write(0x1010000, struct.pack('<3I', 0x1000100, 0x1004010, 0))
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    vm.reg_write(UC_X86_REG_ECX, 0x1006000)
    values = []
    writes = 0

    def ret(arguments, value=1):
        sp = vm.reg_read(UC_X86_REG_ESP)
        target = struct.unpack('<I', vm.mem_read(sp, 4))[0]
        vm.reg_write(UC_X86_REG_ESP, sp+4+arguments)
        vm.reg_write(UC_X86_REG_EAX, value)
        vm.reg_write(UC_X86_REG_EIP, target)

    def hook(uc, ip, size, user):
        nonlocal writes
        sp = uc.reg_read(UC_X86_REG_ESP)
        if ip == 0x1000100:
            uc.emu_stop()
        elif ip == 0x449210:
            ret(0, 0x1001000)
        elif ip == 0x1000200:
            ret(0, 0x1004000)
        elif ip == 0x402C50:
            ret(0, struct.unpack('<I', uc.mem_read(sp+4, 4))[0])
        elif ip == 0x402DB0:
            out = struct.unpack('<I', uc.mem_read(sp+4, 4))[0]
            put(out, 0x1004010)
            ret(0, out)
        elif ip in (0x403C50, 0x403210):
            out = uc.reg_read(UC_X86_REG_ECX)
            put(out, 0x1004010)
            ret(4 if ip == 0x403C50 else 8, out)
        elif ip == 0x404DA0:
            out, old_string, value = struct.unpack('<3I', uc.mem_read(sp+4, 12))
            values.append(value)
            put(out, 0x1004010)
            ret(12, out)
        elif ip == 0x1000300:
            writes += 1
            ret(16)
        elif ip == 0x58DBD2:
            ret(0)
        elif not (0x41E510 <= ip <= 0x41F594 or 0x4246A0 <= ip < 0x424B20
                  or 0x40C110 <= ip < 0x40C380 or 0x42B090 <= ip < 0x444400):
            raise RuntimeError(f'Unexpected export target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x41E510, 0x1000101, count=500000)
    if vm.reg_read(UC_X86_REG_EIP) != 0x1000100:
        raise RuntimeError('Export did not reach return')
    exported = bytes(values)
    header = raw[:61]+raw[62:78]+bytes(4)
    if len(exported) != 2621 or exported[:81] != header or exported[2281:] != raw[0x8EA:0xA3E]:
        raise RuntimeError('Export header/LED field mapping mismatch')
    for index in range(275):
        event = exported[81+index*8:89+index*8]
        expected = (bytes([raw[0x52+index]])+raw[0x278+index*4:0x27C+index*4]
                    +raw[0x6C4+index*2:0x6C6+index*2])
        if event[:1]+event[2:] != expected:
            raise RuntimeError(f'Export event field mismatch at {index}')
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, fixture=args.fixture, synthetic_raw_hex=raw.hex(),
                          exported_values=values, file_write_calls=writes,
                          verified_event_fields=275*7, reserved_header_bytes_zeroed=[77,78,79,80]), indent=2))


if __name__ == '__main__':
    main()
