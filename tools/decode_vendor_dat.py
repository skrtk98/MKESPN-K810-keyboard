"""Inspect native DAT v3 files through the vendor byte dispatcher and VK converter.

Produces research JSON only. Does not configure a device or execute macros.
Missing declared rows are reported, not silently treated as valid macros.
"""
import argparse
import configparser
import hashlib
import json
from pathlib import Path
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ECX, UC_X86_REG_EDX, UC_X86_REG_EBP,
                              UC_X86_REG_ESP, UC_X86_REG_EIP)
from verify_vendor import KNOWN_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('dat', type=Path)
    parser.add_argument('--layout', type=int, choices=range(25), default=1)
    args = parser.parse_args()
    source = args.executable.read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown vendor executable')
    document = configparser.ConfigParser(interpolation=None)
    document.read_string(args.dat.read_text(encoding='ascii'))
    if document.getint('Init', 'DAT_VER', fallback=0) != 3:
        raise ValueError('Only DAT_VER=3 is covered by this research decoder')
    count = document.getint('Macros', 'macroNum')
    if not 0 <= count <= 1000:
        raise ValueError('Unreasonable macro count')
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_EBP, 0x1011000)
    vm.mem_write(0x63D9B3, b'\x03')
    vm.mem_write(0x63B978, struct.pack('<I', args.layout))

    def hook(uc, ip, size, user):
        if ip == 0x41DEF1:
            uc.emu_stop()
        elif not (0x41DB9A <= ip <= 0x41DEF1 or 0x424800 <= ip < 0x424AB0
                  or 0x43B620 <= ip < 0x444400):
            raise RuntimeError(f'Unexpected DAT conversion target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    output = []
    missing = []
    for slot in range(count):
        if str(slot) not in document['Macros']:
            missing.append(slot)
            continue
        text = document['Macros'][str(slot)]
        if len(text) > 26646 or len(text) % 3 or not text.isascii() or not text.isdigit():
            raise ValueError(f'Invalid decimal triplets at macro {slot}')
        values = [int(text[i:i+3]) for i in range(0, len(text), 3)]
        if any(value > 255 for value in values):
            raise ValueError(f'Byte outside 0..255 at macro {slot}')
        vm.mem_write(0x63DE08, bytes(0xB92))
        for index in range(2621):
            for offset, value in ((0x30, 0), (0x38, index), (0x48, 0), (0x74, 15), (0x78, 68)):
                vm.mem_write(0x1011000-offset, struct.pack('<I', value))
            vm.mem_write(0x1011000-0x39, b'\x03')
            vm.reg_write(UC_X86_REG_ESP, 0x1010000)
            vm.reg_write(UC_X86_REG_EBP, 0x1011000)
            vm.reg_write(UC_X86_REG_ECX, values[index] if index < len(values) else 0)
            vm.reg_write(UC_X86_REG_EDX, index)
            vm.emu_start(0x41DB9A, 0x41DEF2, count=1000)
            if vm.reg_read(UC_X86_REG_EIP) != 0x41DEF1:
                raise RuntimeError('DAT dispatcher did not return')
        raw = bytes(vm.mem_read(0x63DE08, 0xB92))
        name = raw[:60].decode('utf-16le', errors='replace').split('\0', 1)[0]
        event_count = struct.unpack_from('<H', raw, 0x40)[0]
        events = [dict(type=raw[0x52+i], code=raw[0x165+i],
                       parameter_hex=raw[0x278+i*4:0x27C+i*4].hex(),
                       delay_ms=struct.unpack_from('<H', raw, 0x6C4+i*2)[0])
                  for i in range(min(event_count, 275))]
        output.append(dict(slot=slot, name=name, source_bytes=len(values),
                           mode_flags=raw[0x3C], repeat=struct.unpack_from('<H', raw, 0x3E)[0],
                           declared_event_count=event_count, events=events,
                           ignored_source_tail=max(0, len(values)-2621),
                           internal_sha256=hashlib.sha256(raw).hexdigest()))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, layout_id=args.layout, macros=output,
                          missing_declared_rows=missing, declared_macros=count), indent=2))


if __name__ == '__main__':
    main()
