"""Map macro flag bits through original UI branches and Apply, without HID.

Names of repeat modes are established separately from the skin definitions.
Bit 2 is deliberately unnamed: output encoding does not prove firmware meaning.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EIP
from trace_vendor_apply import trace
from verify_vendor import KNOWN_SHA256


def ui_cases(source):
    pe=pefile.PE(data=source,fast_load=True)
    vm=Uc(UC_ARCH_X86,UC_MODE_32)
    vm.mem_map(0x400000,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000,pe.get_memory_mapped_image())
    vm.mem_map(0x1000000,0x20000)
    def hook(uc,ip,size,user):
        if ip in (0x41619E,0x4161EF,0x41622B): uc.emu_stop()
        elif not 0x416167<=ip<=0x41622B:
            raise RuntimeError(f'Unexpected UI target {ip:x}')
    vm.hook_add(UC_HOOK_CODE,hook)
    cases=[]
    for initial in (0,4,8,0xFC,0xFF):
        for button in (10,11,12):
            vm.mem_write(0x61F0EC,struct.pack('<I',button))
            vm.mem_write(0x63DE00,bytes(4))
            vm.mem_write(0x63DE44,bytes([initial]))
            vm.reg_write(UC_X86_REG_ESP,0x1010000)
            vm.emu_start(0x416167,0x41622C,count=100)
            assert vm.reg_read(UC_X86_REG_EIP) in (0x41619E,0x4161EF,0x41622B)
            result=vm.mem_read(0x63DE44,1)[0]
            expected=((initial&0xF8)+(2 if button==10 else 1)) if button!=12 else initial&0xF4
            assert result==expected
            cases.append(dict(initial=initial,button=button,result=result))
    return cases


def main():
    source=Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest()!=KNOWN_SHA256:
        raise ValueError('Unknown executable')
    output=[]
    for flags in list(range(8))+[8,16,32,64,128,0xFC,0xFD,0xFE,0xFF]:
        raw=bytearray(0xB92)
        raw[0x3C]=flags
        struct.pack_into('<HH',raw,0x3E,7,2)
        raw[0x52:0x54]=bytes([1,2]); raw[0x165:0x167]=bytes([4,4])
        struct.pack_into('<HH',raw,0x6C4,8,8)
        writes=[e for e in trace(source,macro=bytes(raw)) if 'write_address' in e]
        descriptor=bytes.fromhex(next(e['data'] for e in writes if e['write_address']==0x1D8))[:5]
        payload=bytes.fromhex(next(e['data'] for e in writes if e['write_address']==0x240))
        mode=flags&3
        expected=bytes([7,2|(0x80 if mode==2 else 0),0x40,
                        2|(0x80 if mode==1 else 0)|(0x40 if flags&4 else 0),0])
        assert descriptor==expected,(flags,descriptor.hex(),expected.hex())
        assert payload==bytes([1 if mode in (1,2) else 7,0,0x81,4,1,4,0,0]),payload.hex()
        output.append(dict(internal_flags=flags,descriptor=descriptor.hex(),payload=payload.hex()))
    print(json.dumps(dict(source_sha256=KNOWN_SHA256,serializer_cases=output,
                          ui_cases=ui_cases(source),bit2_firmware_semantics='unresolved'),indent=2))


if __name__=='__main__':
    main()
