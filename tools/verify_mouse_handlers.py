"""Extract button codes from original mouse insertion UI handlers (not labels)."""
import hashlib,json,struct,sys
from pathlib import Path
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP
from verify_vendor import KNOWN_SHA256


def capture(source,entry):
    if hashlib.sha256(source).hexdigest()!=KNOWN_SHA256:raise ValueError('Unknown executable')
    pe=pefile.PE(data=source,fast_load=True);vm=Uc(UC_ARCH_X86,UC_MODE_32)
    vm.mem_map(0x400000,(pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000,pe.get_memory_mapped_image());vm.mem_map(0x1000000,0x20000)
    vm.mem_write(0x63b9a8,bytes(4));vm.mem_write(0x63b994,struct.pack('<I',0x1008000))
    vm.mem_write(0x5be6ac,struct.pack('<I',0x1000100))
    vm.mem_write(0x1010000,struct.pack('<I',0x1000200))
    vm.reg_write(UC_X86_REG_ESP,0x1010000);vm.reg_write(UC_X86_REG_ECX,0x1008000)
    result=[]
    def ret(n):
        sp=vm.reg_read(UC_X86_REG_ESP);ip=struct.unpack('<I',vm.mem_read(sp,4))[0]
        vm.reg_write(UC_X86_REG_ESP,sp+4+n);vm.reg_write(UC_X86_REG_EIP,ip);vm.reg_write(UC_X86_REG_EAX,0)
    def hook(uc,ip,size,user):
        if ip==0x1000200:uc.emu_stop()
        elif ip==0x40e360:
            sp=uc.reg_read(UC_X86_REG_ESP);args=struct.unpack('<4I',uc.mem_read(sp+4,16))
            result.append(dict(code=args[2],event_type=args[3]));ret(16)
        elif ip==0x406db0:ret(4)
        elif ip==0x1000100:ret(16)
        elif not entry<=ip<entry+0x100:raise RuntimeError(f'Unexpected handler target {ip:x}')
    vm.hook_add(UC_HOOK_CODE,hook);vm.emu_start(entry,0x1000201,count=1000)
    if len(result)!=1:raise RuntimeError('Expected one insertion')
    return result[0]


def menu_handlers(source):
    """Resolve English menu roles through command IDs and the MFC message map."""
    pe=pefile.PE(data=source);memory=pe.get_memory_mapped_image()
    menus=next(t for t in pe.DIRECTORY_ENTRY_RESOURCE.entries if t.id==4)
    resource=next(r for r in menus.directory.entries if r.id==200).directory.entries[0].data.struct
    raw=memory[resource.OffsetToData:resource.OffsetToData+resource.Size];position=4;items=[]
    def word():
        nonlocal position
        v=struct.unpack_from('<H',raw,position)[0];position+=2;return v
    def text():
        values=[]
        while (v:=word()):values.append(v)
        return ''.join(chr(v) for v in values).strip()
    def branch(path):
        while position<len(raw):
            flags=word();command=None if flags&16 else word();label=text()
            if flags&16:branch(path+[label])
            else:items.append((path,label,command))
            if flags&128:return
    branch([])
    output=[]
    for path,label,command in items:
        if not 0x8027<=command<=0x802c:continue
        button=next((name for name in ('left','right','middle') if path[-1].lower().startswith(name)),None)
        if button is None:raise RuntimeError('Unknown original mouse menu role')
        needle=struct.pack('<4I',0x111,0,command,command);at=memory.find(needle)
        if at<0:raise RuntimeError('MFC command handler not found')
        entry=struct.unpack_from('<I',memory,at+20)[0]
        output.append(dict(button=button,down='↓' in label,command_id=hex(command),menu_path=path+[label],entry=hex(entry),**capture(source,entry)))
    if len(output)!=6:raise RuntimeError('Expected six menu-derived handlers')
    return output


if __name__=='__main__':
    source=Path(sys.argv[1]).read_bytes()
    cases=menu_handlers(source)
    Path('tests/vendor_mouse_handler_vectors.json').write_text(json.dumps(dict(source_sha256=KNOWN_SHA256,cases=cases),indent=2)+'\n')
    print('Traced six original UI insertion handlers')
