"""Enumerate 25 vendor VK conversion branches in Unicorn; no OS/HID calls."""
import hashlib
import json
from pathlib import Path
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP
from verify_vendor import KNOWN_SHA256


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    targets = set()

    def hook(uc, ip, size, user):
        if ip == 0x1000100:
            uc.emu_stop()
        elif 0x43B620 <= ip < 0x444400:
            targets.add(ip)
        elif not 0x424800 <= ip < 0x424AB0:
            raise RuntimeError(f'Unexpected keyboard converter target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    layouts = []
    for layout in range(25):
        vm.mem_write(0x63B978, struct.pack('<I', layout))
        tables = []
        for argument in (0, 1):
            codes = []
            for vk in range(256):
                vm.mem_write(0x1010000, struct.pack('<3I', 0x1000100, vk, argument))
                vm.reg_write(UC_X86_REG_ESP, 0x1010000)
                vm.reg_write(UC_X86_REG_ECX, 0x1004000)
                vm.emu_start(0x424800, 0x1000101, count=1000)
                if vm.reg_read(UC_X86_REG_EIP) != 0x1000100:
                    raise RuntimeError('VK conversion did not return')
                codes.append(vm.reg_read(UC_X86_REG_EAX)&255)
            tables.append(dict(second_argument=argument, codes=codes))
        layouts.append(dict(layout=layout, tables=tables))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, cases=25*2*256,
                          executed_function_instructions=len(targets), layouts=layouts), indent=2))


if __name__ == '__main__':
    main()
