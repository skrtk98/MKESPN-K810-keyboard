"""Catalog active skin controls and native menu command IDs without running PE."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import pefile
from verify_vendor import KNOWN_SHA256


def read_text(path):
    data = path.read_bytes()
    return data.decode('utf-16') if data[:2] in (b'\xff\xfe', b'\xfe\xff') else data.decode('gb18030')


def menu_items(raw):
    version, offset = struct.unpack_from('<2H', raw)
    if version != 0:
        raise ValueError(f'Unsupported extended menu version {version}')
    position = 4+offset
    output = []

    def word():
        nonlocal position
        value = struct.unpack_from('<H', raw, position)[0]
        position += 2
        return value

    def branch(path):
        nonlocal position
        while position < len(raw):
            flags = word()
            command = None if flags & 16 else word()
            start = position
            while word():
                pass
            label = raw[start:position-2].decode('utf-16le').strip()
            if flags & 16:
                branch(path+[label])
            elif command:
                output.append(dict(path=path, label=label, command_id=hex(command)))
            if flags & 128:
                return
        raise ValueError('Unterminated native menu')

    branch([])
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('skin_root', type=Path)
    args = parser.parse_args()
    data = args.executable.read_bytes()
    if hashlib.sha256(data).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown binary')
    pe = pefile.PE(data=data)
    memory = pe.get_memory_mapped_image()
    controls = []
    text_bindings = []
    for path in sorted(args.skin_root.glob('*.ini')):
        section = ''
        for line in read_text(path).splitlines():
            line = line.strip()
            if line.startswith('[') and line.endswith(']'):
                section = line[1:-1]
            match = re.match(r'^(\d+)\s*=\s*(.*)', line)
            if match and section in ('BUTTONPOS', 'EDIT', 'MACRODISPLAY'):
                entry = dict(file=path.name, section=section, id=int(match[1]), definition=match[2])
                parts = match[2].split(',')
                if len(parts) >= 6 and all(re.fullmatch(r'\s*-?\d+\s*', part) for part in parts[1:5]):
                    controls.append(entry)
                else:
                    text_bindings.append(entry)
    menus = []
    resources = next(t for t in pe.DIRECTORY_ENTRY_RESOURCE.entries if t.id == 4)
    for item in resources.directory.entries:
        for language in item.directory.entries:
            resource = language.data.struct
            raw = memory[resource.OffsetToData:resource.OffsetToData+resource.Size]
            commands = menu_items(raw)
            for command in commands:
                value = int(command['command_id'], 16)
                needle = struct.pack('<4I', 0x111, 0, value, value)
                at = 0
                handlers = []
                while (at := memory.find(needle, at)) != -1:
                    handlers.append(hex(struct.unpack_from('<I', memory, at+20)[0]))
                    at += 1
                command['candidate_handlers'] = sorted(set(handlers))
            menus.append(dict(resource_id=item.id, language=language.id, commands=commands))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, skin_controls=controls,
                          text_bindings=text_bindings, menus=menus,
                          counts=dict(active_controls=len(controls), menu_resources=len(menus),
                                      menu_commands=sum(len(m['commands']) for m in menus))), indent=2))


if __name__ == '__main__':
    main()
