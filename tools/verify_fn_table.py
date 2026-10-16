"""Locate the 12 Fn action bytes using the original Apply serializer, no HID."""
import hashlib
import json
from pathlib import Path
import sys
from verify_vendor import KNOWN_SHA256
from verify_control_flags import image


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    baseline = image(source, {})
    cases = []
    for index in range(12):
        after = image(source, {}, byte_state={0x63D9A4+index: 0xC9})
        changes = [(i,a,b) for i,(a,b) in enumerate(zip(baseline,after)) if a != b]
        assert changes == [(0xE8+index, 0, 0xC9)], changes
        cases.append(dict(index=index, internal_address=hex(0x63D9A4+index),
                          config_offset=hex(0xE8+index), absolute_address=hex(0x1C8+index)))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, cases=cases,
                          action_code=0xC9, scope='Original Apply, synthetic states'), indent=2))


if __name__ == '__main__':
    main()
