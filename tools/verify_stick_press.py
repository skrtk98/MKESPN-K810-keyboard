"""Reproduce hidden-column evidence with the known vendor PE, without USB I/O.

Usage: uv run --group research python tools/verify_stick_press.py APP.exe SKIN_ROOT
"""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_ESI

from verify_vendor import KNOWN_SHA256, emulate_table


def kbd_mode(executable):
    """Execute the exact UTF-16 literal comparison and conversion branch."""
    pe = pefile.PE(data=executable, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_EBP, 0x1011000)
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    vm.mem_write(0x1011008, struct.pack('<I', 0x1001000))
    vm.mem_write(0x1001000, 'KBD Mode\0'.encode('utf-16le'))

    def hook(uc, ip, size, user):
        if ip == 0x40AB93:
            uc.emu_stop()
        elif not 0x40A7C1 <= ip <= 0x40A808:
            raise RuntimeError(f'Unexpected code target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x40A7C1, 0x40AB94, count=200)
    result = vm.reg_read(UC_X86_REG_ESI)
    if result != 0xF4:
        raise RuntimeError('KBD Mode conversion mismatch')
    return result


def main():
    executable = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(executable).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown binary; address assumptions rejected')
    skin = Path(sys.argv[2])
    active = []
    for line in (skin / 'KB.ini').read_text(encoding='utf-16').splitlines():
        match = re.match(r'^(\d+)=([^,]+),', line)
        if match:
            active.append({'id': int(match[1]), 'name': match[2]})
    if len(active) != 18:
        raise RuntimeError('Unexpected active control inventory')
    table = emulate_table(executable)
    hidden = table[16:18]
    # Synthetic row-major dwords 0..159 must become column-major bytes.
    for column, block in zip((16, 17), hidden):
        expected = bytes(column + row * 20 for row in range(8))
        if block['address'] != 0x128 + column * 8 or block['data'] != expected.hex():
            raise RuntimeError('Hidden-column serialization mismatch')
    print(json.dumps({'source_sha256': KNOWN_SHA256, 'active_controls': active,
                      'kbd_mode_code': kbd_mode(executable),
                      'synthetic_hidden_columns': hidden}, indent=2))


if __name__ == '__main__':
    main()
