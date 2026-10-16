"""Inspect GUI message routing and highlight state in the known vendor PE."""
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_32
import pefile

from verify_vendor import KNOWN_SHA256


def main():
    data = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(data).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    pe = pefile.PE(data=data)
    mapped = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    names = {0xF: 'WM_PAINT', 0x200: 'WM_MOUSEMOVE', 0x201: 'WM_LBUTTONDOWN',
             0x202: 'WM_LBUTTONUP', 0x113: 'WM_TIMER', 0x219: 'WM_DEVICECHANGE',
             0x100: 'WM_KEYDOWN', 0x101: 'WM_KEYUP', 0xFF: 'WM_INPUT'}
    messages = []
    for address in range(0x5BF858, 0x5C0000, 24):
        message, code, first, last, signature, handler = struct.unpack_from('<6I', mapped, address-base)
        if not any((message, code, first, last, signature, handler)):
            break
        messages.append(dict(message=hex(message), name=names.get(message),
                             handler=hex(handler), first_id=first, last_id=last))
    else:
        raise ValueError('Message map did not terminate')
    actual = {int(item['message'], 16): int(item['handler'], 16) for item in messages}
    expected = {0x200: 0x41AF50, 0x201: 0x415A40, 0x202: 0x416730, 0xF: 0x41B240}
    if any(actual.get(message) != handler for message, handler in expected.items()):
        raise ValueError('Unexpected GUI message routing')
    writes = []
    disassembler = Cs(CS_ARCH_X86, CS_MODE_32)
    disassembler.skipdata = True
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        for address, size, mnemonic, operands in disassembler.disasm_lite(section.get_data(), base+section.VirtualAddress):
            if mnemonic == 'mov' and re.match(r'dword ptr \[0x(61f0e8|63b988|63dc38)\],', operands):
                writes.append(dict(address=hex(address), instruction=f'{mnemonic} {operands}'))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, main_message_map=messages,
                          highlight_state_writes=writes,
                          key_assignment_message_processor='0x429340',
                          macro_record_message_processor='0x423170'), indent=2))


if __name__ == '__main__':
    main()
