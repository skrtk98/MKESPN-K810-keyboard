"""Map the native DAT byte dispatcher with bounded x86 emulation, no I/O.

The VK conversion call is intercepted as an identity operation: this tool
proves field placement/ignored bytes, not keyboard-layout conversion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import (UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_EDX,
                              UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP)
from verify_vendor import KNOWN_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--version', type=int, choices=(0, 3), default=3)
    args = parser.parse_args()
    source = args.executable.read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown binary')
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_EBP, 0x1011000)
    writes = []
    translated = False

    def code(uc, ip, size, user):
        nonlocal translated
        if ip == 0x41DEF1:
            uc.emu_stop()
        elif ip == 0x424800:
            translated = True
            sp = uc.reg_read(UC_X86_REG_ESP)
            target = struct.unpack('<I', uc.mem_read(sp, 4))[0]
            uc.reg_write(UC_X86_REG_EAX, 0x5A)
            uc.reg_write(UC_X86_REG_ESP, sp+12)
            uc.reg_write(UC_X86_REG_EIP, target)
        elif not 0x41DB9A <= ip <= 0x41DEF1:
            raise RuntimeError(f'Unexpected DAT dispatch target {ip:x}')

    def write(uc, kind, address, size, value, user):
        writes.append([address-0x63DE08, size])

    vm.hook_add(UC_HOOK_CODE, code)
    vm.hook_add(UC_HOOK_MEM_WRITE, write, begin=0x63DE08, end=0x63DE08+0xB92-1)
    mapping = []
    length = 0x22B3 if args.version == 3 else 0x22A1
    vm.mem_write(0x63D9B3, bytes([args.version]))
    for index in range(length):
        writes.clear()
        translated = False
        vm.mem_write(0x63DE08, bytes(0xB92))
        for offset, value in ((0x30, 0), (0x38, index), (0x48, 0), (0x74, 15), (0x78, 68)):
            vm.mem_write(0x1011000-offset, struct.pack('<I', value))
        vm.mem_write(0x1011000-0x39, bytes([args.version]))
        vm.reg_write(UC_X86_REG_ESP, 0x1010000)
        vm.reg_write(UC_X86_REG_EDX, index)
        vm.reg_write(UC_X86_REG_ECX, 0x5A)
        vm.emu_start(0x41DB9A, 0x41DEF2, count=500)
        if vm.reg_read(UC_X86_REG_EIP) != 0x41DEF1:
            raise RuntimeError('Dispatcher did not reach bounded exit')
        mapping.append(dict(index=index, writes=list(writes), vk_conversion=translated))
    # The vendor uses this as the parsed-byte loop bound and requests THREE
    # times this many text characters. Do not silently "fix" that behavior.
    ignored = [item['index'] for item in mapping if not item['writes']]
    if args.version == 3 and ignored != list(range(2621, length)):
        raise RuntimeError('Unexpected v3 ignored range')
    samples = [0, 59, 60, 61, 62, 72, 73, 74, 75, 80, 81, 82, 83,
               2280, 2281, 2620, 2621, 2960]
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, version=args.version,
                          dispatcher_loop_bound=length, text_buffer_limit=length*3,
                          ignored_range=[min(ignored), max(ignored)] if ignored else None,
                          samples=[mapping[i] for i in samples],
                          mapping_sha256=hashlib.sha256(json.dumps(mapping,sort_keys=True).encode()).hexdigest()), indent=2))


if __name__ == '__main__':
    main()
