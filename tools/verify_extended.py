"""Generate independent single-action and macro serializer fixtures from x86."""
import hashlib
import json
from pathlib import Path
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBX, UC_X86_REG_ESP, UC_X86_REG_EIP
from trace_vendor_apply import trace
from verify_vendor import KNOWN_SHA256

LABELS = ['Play/Pause','Vol-','Vol+','Previous','Next','Player','Mail','WWW Forward',
          'WWW Stop','WWW Back','WWW Refresh','WWW Research','WWW Favorite','Mute',
          'My Computer','Stop','Calculator','Web Browser','Full-key Locked',
          'Backlight Mode Switch','Backlight Color Switch','Speed +','Speed -',
          'Brightness +','Brightness -','Backlight On/Off']


def action(executable, choice):
    pe = pefile.PE(data=executable, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000,pe.get_memory_mapped_image())
    vm.mem_map(0x1000000,0x20000)
    for i,label in enumerate(LABELS):
        at=0x1002000+i*256
        vm.mem_write(at,label.encode('utf-16le')+b'\0\0')
        vm.mem_write(0x6478C8+i*4,struct.pack('<I',at))
    vm.mem_write(0x1010000,struct.pack('<2I',0,0x1002000+choice*256))
    vm.reg_write(UC_X86_REG_ESP,0x1010000)
    def hook(uc,ip,size,user):
        if ip==0x4084E9:
            uc.emu_stop()
        elif ip==0x403D50:
            sp=uc.reg_read(UC_X86_REG_ESP)
            target,left,right=struct.unpack('<3I',uc.mem_read(sp,12))
            a=struct.unpack('<I',uc.mem_read(left,4))[0]
            b=struct.unpack('<I',uc.mem_read(right,4))[0]
            uc.reg_write(UC_X86_REG_EAX,int(bytes(uc.mem_read(a,120))==bytes(uc.mem_read(b,120))))
            uc.reg_write(UC_X86_REG_ESP,sp+4)
            uc.reg_write(UC_X86_REG_EIP,target)
        elif not 0x4080E0<=ip<0x4084E9:
            raise RuntimeError(f'Unexpected action target {ip:x}')
    vm.hook_add(UC_HOOK_CODE,hook)
    vm.emu_start(0x4080E0,0x4084EA,count=5000)
    return {'label':LABELS[choice],'unique_index':choice,'code':vm.reg_read(UC_X86_REG_EBX)&255}


def macro(executable, spec):
    raw=bytearray(0xB92)
    # skin_mac.ini: button 10 RELEASE -> 2 at 416184;
    # button 11 CLICK -> 1 at 4161d5. Do not infer enum order from labels.
    raw[0x3C]={'repeat':0,'while-held':2,'until-click':1}[spec.get('mode','repeat')]
    struct.pack_into('<H',raw,0x3E,spec.get('repeat',1))
    events=spec['events']
    struct.pack_into('<H',raw,0x40,len(events))
    xy=wheel=0
    for i,event in enumerate(events):
        kind=event['type']; x=y=0
        if kind in ('key-down','key-up','mouse-down','mouse-up'):
            typ=1 if kind.endswith('down') else 2
            code=event.get('code',4)
        elif kind=='scroll':
            code=0xF7;typ=7 if event['steps']>=0 else 8;x=abs(event['steps']);wheel+=1
        elif kind=='move':
            code=0xF6;x=abs(event['x']);y=abs(event['y']);xy+=1
            typ={(False,False):6,(True,False):4,(False,True):5,(True,True):3}[(event['x']<0,event['y']<0)]
        elif kind=='delay':
            typ=2;code=0
        else:
            raise ValueError(kind)
        raw[0x52+i]=typ;raw[0x165+i]=code
        struct.pack_into('<HH',raw,0x278+i*4,x,y)
        struct.pack_into('<H',raw,0x6C4+i*2,event.get('delay',8))
    struct.pack_into('<H',raw,0x42,xy)
    struct.pack_into('<H',raw,0x44,wheel)
    events=trace(executable,macro=bytes(raw))
    writes=[e for e in events if 'write_address' in e]
    descriptor=next(e for e in writes if e['write_address']==0x1D8)['data'][:10]
    payload=[e for e in writes if e['write_address']>=0x240]
    return {'spec':spec,'descriptor':descriptor,'payload':''.join(e['data'] for e in payload)}


def repeat_button(executable, button):
    """Read the actual skin button handlers before any MFC/UI call."""
    pe=pefile.PE(data=executable,fast_load=True)
    vm=Uc(UC_ARCH_X86,UC_MODE_32)
    vm.mem_map(0x400000,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000,pe.get_memory_mapped_image())
    vm.mem_map(0x1000000,0x20000);vm.reg_write(UC_X86_REG_ESP,0x1010000)
    vm.mem_write(0x61f0ec,struct.pack('<I',button));vm.mem_write(0x63de00,bytes(4))
    vm.mem_write(0x63de44,bytes(1))
    def hook(uc,ip,size,user):
        if ip in (0x41619e,0x4161ef,0x41622b):uc.emu_stop()
        elif not 0x416167<=ip<=0x41622b:raise RuntimeError(f'Unexpected mode handler {ip:x}')
    vm.hook_add(UC_HOOK_CODE,hook)
    vm.emu_start(0x416167,0x41622c,count=100)
    return dict(button=button,mode=vm.mem_read(0x63de44,1)[0]&3)


if __name__=='__main__':
    executable=Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(executable).hexdigest()!=KNOWN_SHA256:
        raise SystemExit('Unknown binary')
    specs=[{'events':[{'type':'key-down','code':4},{'type':'key-up','code':4}]},
           {'events':[{'type':'mouse-down','code':0xF1},{'type':'mouse-up','code':0xF1}]},
           {'events':[{'type':'scroll','steps':1},{'type':'scroll','steps':-3}]},
           {'events':[{'type':'move','x':-20,'y':10},{'type':'move','x':20,'y':-10}]},
           {'events':[{'type':'delay','delay':10000}]},
           {'events':[{'type':'key-down','code':0xE0},{'type':'key-down','code':6},
                      {'type':'key-up','code':6},{'type':'key-up','code':0xE0}]}]
    specs += [dict(specs[0],mode=mode,repeat=3) for mode in ('repeat','while-held','until-click')]
    result={'source_sha256':KNOWN_SHA256,'repeat_buttons':[repeat_button(executable,b) for b in (10,11,12)],'actions':[action(executable,i) for i in range(26)],
            'macros':[macro(executable,s) for s in specs]}
    Path('tests/vendor_extended_vectors.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print('Generated action and macro serializer fixtures')
