"""Trace generic macro extension records without executing vendor I/O."""
import json,struct,sys
from pathlib import Path
from trace_vendor_apply import trace
from verify_vendor import KNOWN_SHA256


def capture(source,name,code,types,parameters,led=None,gpio=None):
    raw=bytearray(0xb92);struct.pack_into('<H',raw,0x3e,1)
    struct.pack_into('<H',raw,0x40,len(types))
    if code==0xfa:struct.pack_into('<H',raw,0x48,len(types))
    for i,(typ,param) in enumerate(zip(types,parameters)):
        raw[0x52+i]=typ;raw[0x165+i]=code
        struct.pack_into('<H',raw,0x278+i*4,param)
        struct.pack_into('<H',raw,0x6c4+i*2,8)
    if led is not None:raw[0x4a]=1;raw[0x8ea:0x8ea+len(led)]=led
    if gpio is not None:raw[0x4b]=1;raw[0xa3e:0xa3e+len(gpio)]=gpio
    writes=[e for e in trace(source,macro=bytes(raw)) if 'write_address' in e]
    return dict(name=name,code=code,types=types,parameters=parameters,
                led_hex=led.hex() if led is not None else None,
                gpio_hex=gpio.hex() if gpio is not None else None,
                writes=[e for e in writes if e['write_address']>=0x1d8])


if __name__=='__main__':
    source=Path(sys.argv[1]).read_bytes()
    vectors=[capture(source,'media-volume-up',0xfa,[11,12],[0xe9,0xe9])]
    vectors += [capture(source,f'led-type-{typ}',0xf9,[typ],[0],led=bytes([1,0,0,0,2,1,10,1])) for typ in (13,14,15)]
    vectors += [capture(source,'led-two-patterns',0xf9,[13],[0],led=bytes([2,0,0,0,0,1,10,1,2,1,20,1]))]
    # GPIO has no exposed pins in the K810 UI; synthetic serialization only.
    vectors += [capture(source,'gpio-structure-only',0xfb,[16],[0],gpio=bytes([1,0,0,0,0,0,0,0]))]
    Path('tests/vendor_macro_extension_vectors.json').write_text(json.dumps(dict(source_sha256=KNOWN_SHA256,cases=vectors),indent=2)+'\n')
    print('Generated macro extension traces')
