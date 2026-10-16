"""Discover and emulate literal-name branches in the vendor key converter."""
import hashlib
import json
from pathlib import Path
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_ESI
import pefile

from verify_vendor import KNOWN_SHA256


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown binary')
    pe = pefile.PE(data=source, fast_load=True)
    memory = pe.get_memory_mapped_image()
    instructions = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm_lite(memory[0x8520:0xAB93], 0x408520))
    output = []
    last_start = None
    for index, (address, size, mnemonic, operands) in enumerate(instructions):
        if mnemonic == 'mov' and operands == 'eax, dword ptr [ebp + 8]':
            last_start = address
        if address < 0x40A000 or mnemonic != 'mov' or not operands.startswith('ecx, 0x5c') or last_start is None:
            continue
        literal = int(operands.split(', ')[1], 16)
        offset = literal - 0x400000
        end = next((i for i in range(offset, min(offset+200, len(memory)), 2)
                    if memory[i:i+2] == b'\0\0'), None)
        if end is None:
            continue
        label = memory[offset:end].decode('utf-16le')
        if not label or not label.isprintable():
            continue
        vm = Uc(UC_ARCH_X86, UC_MODE_32)
        vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
        vm.mem_write(0x400000, memory)
        vm.mem_map(0x1000000, 0x20000)
        vm.reg_write(UC_X86_REG_EBP, 0x1011000)
        vm.reg_write(UC_X86_REG_ESP, 0x1010000)
        vm.mem_write(0x1011008, struct.pack('<I', 0x1001000))
        vm.mem_write(0x1001000, label.encode('utf-16le')+b'\0\0')
        entry = last_start

        def hook(uc, ip, size, user):
            if ip == 0x40AB93:
                uc.emu_stop()
            elif not entry <= ip < entry+0x100:
                raise RuntimeError(f'Unexpected literal conversion target {ip:x}')

        vm.hook_add(UC_HOOK_CODE, hook)
        vm.emu_start(entry, 0x40AB94, count=500)
        output.append(dict(label=label, entry=hex(entry), code=vm.reg_read(UC_X86_REG_ESI)))
    if not output:
        raise ValueError('No literal branches discovered')
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, literal_actions=output), indent=2))


if __name__ == '__main__':
    main()
