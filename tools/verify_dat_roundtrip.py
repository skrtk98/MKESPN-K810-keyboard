"""Round-trip a bounded synthetic macro through original export/import code.

Writes only synthetic research files. Does not execute macros or access HID.
Both child tools validate the vendor executable hash before emulation.
"""
import json
from pathlib import Path
import struct
import subprocess
import sys


def main():
    executable = sys.argv[1]
    tools = Path(__file__).resolve().parent
    exported = json.loads(subprocess.check_output(
        [sys.executable, str(tools/'verify_dat_export.py'), executable,
         '--fixture', 'keyboard'], encoding='utf-8'))
    directory = Path('research/dat-roundtrip')
    directory.mkdir(parents=True, exist_ok=True)
    dat = directory/'synthetic.dat'
    values = exported['exported_values']
    dat.write_text('[Init]\nDAT_VER=3\n[Macros]\nmacroNum=1\n0='
                   + ''.join(f'{value:03d}' for value in values)+'\n', encoding='ascii')
    decoded = json.loads(subprocess.check_output(
        [sys.executable, str(tools/'decode_vendor_dat.py'), executable, str(dat)],
        encoding='utf-8'))
    raw = bytes.fromhex(exported['synthetic_raw_hex'])
    expected_events = [dict(type=raw[0x52+i], code=raw[0x165+i],
                            parameter_hex=raw[0x278+i*4:0x27C+i*4].hex(),
                            delay_ms=struct.unpack_from('<H', raw, 0x6C4+i*2)[0])
                       for i in range(4)]
    macro = decoded['macros'][0]
    assert macro['events'] == expected_events, (macro['events'], expected_events)
    assert macro['name'] == 'K810 roundtrip'
    assert macro['repeat'] == 3 and macro['declared_event_count'] == 4
    assert macro['source_bytes'] == 2621 and not decoded['missing_declared_rows']
    report = dict(source_sha256=exported['source_sha256'], fixture='keyboard',
                  serialized_bytes=len(values), macro=macro,
                  scope='One synthetic EN-layout keyboard macro; not all actions/layouts')
    (directory/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
