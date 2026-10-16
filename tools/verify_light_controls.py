"""Trace Light direction/symmetry click branches in the original vendor code.

This checks handler acceptance, not visibility, firmware support, or light output.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ECX, UC_X86_REG_ESI, UC_X86_REG_EIP
from verify_vendor import KNOWN_SHA256


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    def hook(uc, ip, size, user):
        if ip in (0x41669B, 0x415EFE):
            uc.emu_stop()
        elif not 0x415E63 <= ip < 0x415EFE:
            raise RuntimeError(f'Unexpected Light handler target {ip:x}')
    vm.hook_add(UC_HOOK_CODE, hook)
    controls = [(45, 'symmetry'), (47, 'direction0'), (48, 'direction1'),
                (49, 'direction2'), (50, 'direction3')]
    cases = []
    for mode in range(13):
        accepted = []
        for control, name in controls:
            vm.mem_write(0x6474C4, struct.pack('<2I', 0, 255))
            vm.reg_write(UC_X86_REG_ESI, mode)
            vm.reg_write(UC_X86_REG_ECX, control)
            vm.emu_start(0x415E63, 0x41669C, count=100)
            if vm.reg_read(UC_X86_REG_EIP) not in (0x41669B, 0x415EFE):
                raise RuntimeError('Light branch did not reach bounded exit')
            symmetry, direction = struct.unpack('<2I', vm.mem_read(0x6474C4, 8))
            if symmetry or direction != 255:
                accepted.append(name)
        expected = [] if mode in (0,1,2,4) else [name for _,name in controls
                    if not (name == 'direction2' and mode == 5)
                    and not (name == 'direction3' and mode != 8)]
        assert accepted == expected, (mode, accepted, expected)
        cases.append(dict(mode=mode, handler_accepted=accepted))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, cases=cases,
                          branch_cases=65, scope='Click-handler branch only'), indent=2))


if __name__ == '__main__':
    main()
