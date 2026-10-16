"""Trace table/data placement at multiple macro counts using original Apply.

Synthetic macro data and intercepted EEPROM I/O only; no hardware writes.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
from trace_vendor_apply import trace
from verify_vendor import KNOWN_SHA256


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    raw = bytearray(0xB92)
    struct.pack_into('<HH', raw, 0x3E, 1, 2)
    raw[0x52:0x54] = bytes([1,2])
    raw[0x165:0x167] = bytes([4,4])
    struct.pack_into('<HH', raw, 0x6C4, 8, 8)
    cases = []
    for count,control_flags in [(0,0xC0),(1,0xC0),(18,0xC0),(19,0xC0),(20,0xC0),(20,0x40)]:
        state = {0x62527C: count}
        state.update({0x61F038+i*4: 0 for i in range(20)})
        state.update({0x61F088+i*4: i for i in range(20)})
        writes = [e for e in trace(source, macro=bytes(raw), state=state, flags=control_flags)
                  if 'write_address' in e and e['write_address'] >= 0x1D8]
        table_bytes = ((count+2)*5+7)&~7
        table_writes = writes[:table_bytes//8]
        data_writes = writes[table_bytes//8:]
        assert [e['write_address'] for e in table_writes] == list(range(0x1D8,0x1D8+table_bytes,8))
        assert [e['write_address'] for e in data_writes] == list(range(0x240,0x240+count*8,8))
        assert all(e['data'] == '0100810401040000' for e in data_writes)
        table = b''.join(bytes.fromhex(e['data']) for e in table_writes)
        if count >= 19:
            assert table[100:104] == struct.pack('<I',control_flags), table.hex()
        final = bytearray(8192)
        for e in writes:
            address=e['write_address']; data=bytes.fromhex(e['data'])
            final[address:address+len(data)] = data
        for i in range(count):
            descriptor=final[0x1D8+i*5:0x1DD+i*5]
            assert descriptor == bytes([7,2,(0x240+i*8)&255,(0x240+i*8)>>8,0]), descriptor.hex()
        cases.append(dict(count=count, control_flags=hex(control_flags), table_bytes_written=table_bytes,
                          table_end_exclusive=hex(0x1D8+table_bytes),
                          first_payload=hex(data_writes[0]['write_address']) if data_writes else None,
                          table_payload_overlap_bytes=max(0,0x1D8+table_bytes-0x240) if count else 0,
                          extra_slot_bytes_after_final_writes=final[0x1D8+count*5:0x1D8+(count+2)*5].hex(),
                          bytes_beyond_20_descriptors_before_payload=table[100:].hex(),
                          write_count=len(writes)))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256,cases=cases,
                          scope='Synthetic normal-memory Apply; encoder semantics unproven'),indent=2))


if __name__ == '__main__':
    main()
