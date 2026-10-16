"""Inventory literal INI key references in original profile load/save functions.

Static references do not imply runtime reachability or successful file writes.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
from verify_vendor import KNOWN_SHA256


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    pe = pefile.PE(data=source, fast_load=True)
    mapped = pe.get_memory_mapped_image()
    base = pe.OPTIONAL_HEADER.ImageBase
    output = {}
    for name, start, end in [('load', 0x41BD40, 0x41D1CD),
                             ('save', 0x422430, 0x422CE0)]:
        refs = []
        for address, size, mnemonic, operands in Cs(CS_ARCH_X86, CS_MODE_32).disasm_lite(
                mapped[start-base:end-base], start):
            if mnemonic != 'push' or not re.fullmatch('0x[0-9a-f]+', operands):
                continue
            target = int(operands, 16)
            if not 0x5BF000 <= target < 0x5C2000:
                continue
            raw = mapped[target-base:target-base+160]
            text = raw.decode('utf-16le', errors='replace').split('\0', 1)[0]
            if re.fullmatch('[A-Z][A-Z0-9_]*(?:%d)?', text):
                refs.append(dict(address=hex(address), literal=text))
        cycle_keys = sorted({r['literal'] for r in refs if r['literal'].startswith('HR_LED_MODE_EN')})
        assert cycle_keys == [f'HR_LED_MODE_EN{i}' for i in range(9)], cycle_keys
        output[name] = refs
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, references=output,
                          cycle_ini_keys=list(range(9)),
                          scope='Literal push references in two original functions'), indent=2))


if __name__ == '__main__':
    main()
