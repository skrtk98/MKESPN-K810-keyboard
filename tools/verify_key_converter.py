"""Run the complete vendor label-to-key converter with English INI bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_ESP, UC_X86_REG_EIP
from verify_vendor import KNOWN_SHA256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('index_ini', type=Path)
    parser.add_argument('--fn', action='store_true', help='Trace narrow Fn converter, with two pointer sentinels')
    args = parser.parse_args()
    source = args.executable.read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown binary')
    tables = {'BUTTONPOS': {}, 'UniqueName': {}}
    section = ''
    for line in args.index_ini.read_text(encoding='utf-16').splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'):
            section = line[1:-1]
        match = re.match(r'^(\d+)\s*=\s*(.*)', line)
        if match and section in tables:
            parts = match[2].split(',')
            if len(parts) >= 2:
                tables[section][int(match[1])] = parts[1].strip()
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x80000)
    if args.fn:
        vm.mem_map(0x2000000, 0x2000)
    start = 0x4080E0 if args.fn else 0x408520
    end = 0x4084E9 if args.fn else 0x40AB93
    labels = []
    heap = 0x1020000

    def bind(address, label):
        nonlocal heap
        data = label.encode('utf-16le')+b'\0\0'
        vm.mem_write(heap, data)
        vm.mem_write(address, struct.pack('<I', heap))
        heap += (len(data)+7)&~7

    for section, base, count in (('BUTTONPOS', 0x647648, 160), ('UniqueName', 0x6478C8, 160)):
        for index in range(count):
            label = tables[section].get(index, f'__unused_{section}_{index}')
            bind(base+index*4, label)
            if index in tables[section]:
                labels.append(dict(table=section, index=index, label=label))
    for index in range(20):
        label = f'__macro_{index+1}'
        bind(0x648A18+index*4, label)
        labels.append(dict(table='synthetic macro slots', index=index+1, label=label))

    def text_at(pointer):
        data = bytes(vm.mem_read(pointer, 512))
        stop = next(i for i in range(0, 512, 2) if data[i:i+2] == b'\0\0')
        return data[:stop]

    def hook(uc, ip, size, user):
        if ip == end:
            uc.emu_stop()
        elif ip == 0x403D50:
            sp = uc.reg_read(UC_X86_REG_ESP)
            target, left, right = struct.unpack('<3I', uc.mem_read(sp, 12))
            a = struct.unpack('<I', uc.mem_read(left, 4))[0]
            b = struct.unpack('<I', uc.mem_read(right, 4))[0]
            uc.reg_write(UC_X86_REG_EAX, int(text_at(a) == text_at(b)))
            uc.reg_write(UC_X86_REG_ESP, sp+4)
            uc.reg_write(UC_X86_REG_EIP, target)
        elif not start <= ip < end:
            raise RuntimeError(f'Unexpected converter target {ip:x}')

    vm.hook_add(UC_HOOK_CODE, hook)
    for item in labels:
        codes = []
        for pointer in ([0x1001000, 0x2001000] if args.fn else [0x1001000]):
            vm.mem_write(pointer, item['label'].encode('utf-16le')+b'\0\0')
            vm.mem_write(0x1010000, struct.pack('<2I', 0, pointer))
            vm.reg_write(UC_X86_REG_ESP, 0x1010000)
            vm.emu_start(start, end+1, count=30000)
            if vm.reg_read(UC_X86_REG_EIP) != end:
                raise RuntimeError('Converter did not reach exit')
            codes.append(vm.reg_read(UC_X86_REG_EBX)&255 if args.fn else vm.reg_read(UC_X86_REG_ESI))
        if args.fn:
            item['codes_for_pointer_high_bytes_1_2'] = codes
            item['stable_result'] = codes[0] == codes[1]
        else:
            item['code'] = codes[0]
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, converter='fn' if args.fn else 'matrix',
                          bindings=labels), indent=2))


if __name__ == '__main__':
    main()
