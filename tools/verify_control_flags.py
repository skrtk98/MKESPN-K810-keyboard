"""Map control and Light cycle flags through the original Apply serializer."""
import hashlib
import json
from pathlib import Path
import sys

from trace_vendor_apply import trace
from verify_vendor import KNOWN_SHA256


def image(source, state, byte_state=None):
    result = bytearray(248)
    for item in trace(source, state=state, byte_state=byte_state):
        if 'write_address' not in item:
            continue
        offset = item['write_address'] - 0xE0
        data = bytes.fromhex(item['data'])
        if 0 <= offset and offset+len(data) <= len(result):
            result[offset:offset+len(data)] = data
    return result


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    baseline = image(source, {})
    fields = [('KEYSMODE', 0x61F104, 0), ('BALTF4', 0x63DDD8, 1),
              ('BWINLOCK', 0x63DDE8, 1), ('BALLKEYSLOCK', 0x63DDF0, 1),
              ('BMODELED', 0x63DDF4, 1)]
    # Only slots 0..8 have these literal INI keys. 9..12 are internal slots,
    # consumed by Apply but absent from the current INI load/save functions.
    fields += [(f'HR_LED_MODE_EN{i}' if i < 9 else f'cycle_internal_slot_{i}',
                0x6475C4+i*4, 1) for i in range(13)]
    output = []
    for name, address, value in fields:
        after = image(source, {address: value})
        output.append(dict(name=name, global_address=hex(address), value=value,
                           changes=[dict(offset=hex(i), before=a, after=b, xor=a^b)
                                    for i, (a, b) in enumerate(zip(baseline, after)) if a != b]))
    all_cycles = {0x6475C4+i*4: 1 for i in range(13)}
    all_image = image(source, all_cycles)
    disabled = []
    for i in range(13):
        after = image(source, all_cycles | {0x6475C4+i*4: 0})
        disabled.append(dict(index=i, changes=[dict(offset=hex(j), xor=a^b)
                              for j, (a, b) in enumerate(zip(all_image, after)) if a != b]))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256,
                          synthetic_baseline=baseline.hex(), fields=output,
                          cycle_disable_from_all_enabled=disabled), indent=2))


if __name__ == '__main__':
    main()
