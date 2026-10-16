"""Static HID/input API inventory of the known vendor PE. Never executes it."""
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
        raise ValueError('Unknown executable; address assumptions rejected')
    pe = pefile.PE(data=data)
    names = {'ReadFile', 'WriteFile', 'HidD_GetFeature', 'HidD_SetFeature',
             'HidD_GetInputReport', 'SetWindowsHookExW', 'GetAsyncKeyState',
             'RegisterRawInputDevices', 'GetRawInputData', 'CreateFileW'}
    imports = {item.address: item.name.decode('ascii')
               for dll in pe.DIRECTORY_ENTRY_IMPORT for item in dll.imports
               if item.name and item.name.decode('ascii') in names}
    disassembler = Cs(CS_ARCH_X86, CS_MODE_32)
    disassembler.skipdata = True
    # Keep compact text tuples rather than hundreds of thousands of detailed
    # Capstone objects. The PE contains a statically linked MFC runtime.
    instructions = []
    for section in pe.sections:
        if section.Characteristics & 0x20000000:
            instructions.extend(disassembler.disasm_lite(section.get_data(),
                pe.OPTIONAL_HEADER.ImageBase + section.VirtualAddress))
    thunks = {}
    for address, size, mnemonic, operands in instructions:
        match = re.fullmatch(r'dword ptr \[(0x[0-9a-f]+)\]', operands)
        if mnemonic == 'jmp' and match and int(match[1], 16) in imports:
            thunks[address] = imports[int(match[1], 16)]
    references = []
    nearby_references = []
    for address, size, mnemonic, operands in instructions:
        for literal in re.findall(r'0x[0-9a-f]+', operands):
            target = int(literal, 16)
            name = imports.get(target)
            if target == 0x61F034:
                name = 'FF00 handle / one-based macro-array anchor'
            if mnemonic in ('call', 'jmp'):
                name = name or thunks.get(target)
            if name:
                references.append(dict(address=f'0x{address:08x}', target=name,
                                       instruction=f'{mnemonic} {operands}'))
            if 0x61F020 <= target <= 0x61F034 or 0x624EA8 <= target < 0x624EE8:
                nearby_references.append(dict(address=hex(address),
                                               instruction=f'{mnemonic} {operands}'))
    mapped = pe.get_memory_mapped_image()
    def word(address):
        return struct.unpack_from('<I', mapped, address - pe.OPTIONAL_HEADER.ImageBase)[0]
    def raw_references(value):
        needle = struct.pack('<I', value)
        positions = []
        start = 0
        while (start := mapped.find(needle, start)) != -1:
            positions.append(hex(start + pe.OPTIONAL_HEADER.ImageBase))
            start += 1
        return positions
    locator = word(0x5C9D28)
    descriptor = word(locator + 12)
    start = descriptor - pe.OPTIONAL_HEADER.ImageBase + 8
    class_name = mapped[start:mapped.index(b'\0', start)].decode('ascii')
    names_to_check = ['HidD_GetInputReport', 'ReadFileEx', 'NtReadFile',
                      'DeviceIoControl', 'RegisterRawInputDevices', 'GetRawInputData']
    print(json.dumps(dict(source_sha256=KNOWN_SHA256,
                          imports={hex(a): n for a, n in imports.items()},
                          references=references, nearby_references=nearby_references,
                          raw_references={hex(a): raw_references(a)
                                          for a in (0x61F034, 0x624EA8, 0x46408C)},
                          read_file_virtual_class=class_name,
                          read_file_vtable_entry=hex(word(0x5C9D64)),
                          alternate_api_names={name: any(name.encode(encoding) in mapped
                              for encoding in ('ascii', 'utf-16le')) for name in names_to_check}), indent=2))


if __name__ == '__main__':
    main()
