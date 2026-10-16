"""Compare input/transport API references in three hash-pinned vendor PEs.

Only parses bytes and instructions. No imports are loaded or executed.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

KNOWN = {
    'ef79b5e0ad1786dd682bc8ed1dad4626627c0518639ec67a702088d6322b8e36': 'K810',
    '955cd803aa7c624bca3d9fd7bedcf4558a8139e4c0f125709cd09f88adaadc19': 'K201 reference 01',
    'ffed57d054e941b4543fd00a6ff4d0a068d39823cc1ee742fa033c2a20824b07': 'K201 reference 02',
}
APIS = {'ReadFile', 'WriteFile', 'ReadFileEx', 'NtReadFile', 'DeviceIoControl',
        'HidD_GetFeature', 'HidD_SetFeature', 'HidD_GetInputReport',
        'HidD_SetOutputReport', 'SetWindowsHookExW', 'GetAsyncKeyState',
        'RegisterRawInputDevices', 'GetRawInputData', 'CreateFileW'}
INPUT_HANDLES = {'K810': 0x61F034, 'K201 reference 01': 0x602044,
                 'K201 reference 02': 0x607030}


def inspect(path):
    source = Path(path).read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest not in KNOWN:
        raise ValueError('Unknown executable')
    pe = pefile.PE(data=source)
    imported = {i.address: i.name.decode('ascii')
                for d in pe.DIRECTORY_ENTRY_IMPORT for i in d.imports
                if i.name and i.name.decode('ascii') in APIS}
    instructions = []
    cs = Cs(CS_ARCH_X86, CS_MODE_32)
    cs.skipdata = True
    for section in pe.sections:
        if section.Characteristics & 0x20000000:
            instructions.extend(cs.disasm_lite(section.get_data(),
                pe.OPTIONAL_HEADER.ImageBase+section.VirtualAddress))
    thunks = {}
    for address, size, mnemonic, operand in instructions:
        m = re.fullmatch(r'dword ptr \[(0x[0-9a-f]+)\]', operand)
        if mnemonic == 'jmp' and m and int(m[1],16) in imported:
            thunks[address] = imported[int(m[1],16)]
    references = []
    handle_references = []
    handle = INPUT_HANDLES[KNOWN[digest]]
    for address, size, mnemonic, operand in instructions:
        if handle in [int(literal,16) for literal in re.findall(r'0x[0-9a-f]+',operand)]:
            handle_references.append(dict(address=hex(address), instruction=mnemonic+' '+operand))
        if mnemonic not in ('call','jmp'):
            continue
        for literal in re.findall(r'0x[0-9a-f]+',operand):
            name = imported.get(int(literal,16)) or thunks.get(int(literal,16))
            if name:
                references.append(dict(address=hex(address), api=name))
    return dict(name=KNOWN[digest], sha256=digest, size=len(source),
                image_base=hex(pe.OPTIONAL_HEADER.ImageBase),
                imports=sorted(imported.values()), references=references,
                ff00_handle=hex(handle), ff00_handle_references=handle_references,
                absent_api_name_strings=sorted(name for name in APIS
                    if not any(name.encode(encoding) in source for encoding in ('ascii','utf-16le'))))


def main():
    print(json.dumps([inspect(path) for path in sys.argv[1:]],indent=2))


if __name__ == '__main__':
    main()
