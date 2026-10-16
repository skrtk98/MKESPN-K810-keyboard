"""Emulate the original profile-menu dispatcher with all callees intercepted.

Proves dispatch and reset state changes only, not full callees or hardware.
No vendor executable, file-dialog API, thread, or HID operation is launched.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_ECX, UC_X86_REG_ESP, UC_X86_REG_EIP
from verify_vendor import KNOWN_SHA256


def trace(source, item):
    pe = pefile.PE(data=source, fast_load=True)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage+4095)&~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    def put(address, value):
        vm.mem_write(address, struct.pack('<I', value))
    put(0x1010000, 0x1000100)
    put(0x1010004, 9)
    put(0x1010008, item)
    defaults = bytes((i*11+3)&255 for i in range(640))
    vm.mem_write(0x63D498, defaults)
    put(0x62527C, 7)
    put(0x647634, 0)
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    vm.reg_write(UC_X86_REG_ECX, 0x1003000)
    calls = []
    # stdcall/thiscall stack arguments; cdecl cleanup stays with its caller.
    stubs = {0x40D980: 0, 0x4073A0: 0, 0x404380: 0, 0x4061B0: 0,
             0x402C50: 0, 0x41BD40: 12, 0x44C61D: 24}
    def hook(uc, ip, size, user):
        if ip == 0x1000100:
            uc.emu_stop()
        elif ip in stubs:
            sp = uc.reg_read(UC_X86_REG_ESP)
            calls.append(hex(ip))
            target = struct.unpack('<I', uc.mem_read(sp, 4))[0]
            uc.reg_write(UC_X86_REG_ESP, sp+4+stubs[ip])
            uc.reg_write(UC_X86_REG_EAX, 0)
            uc.reg_write(UC_X86_REG_EIP, target)
        elif not 0x418B50 <= ip < 0x418C70:
            raise RuntimeError(f'Unexpected profile dispatcher target {ip:x}')
    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x418B50, 0x1000101, count=10000)
    if vm.reg_read(UC_X86_REG_EIP) != 0x1000100:
        raise RuntimeError('Dispatcher did not return')
    if item == 3:
        assert vm.mem_read(0x63D718, 640) == defaults
        assert vm.mem_read(0x63D218, 640) == defaults
        assert vm.mem_read(0x63D9B8, 640) == bytes(640)
        assert vm.mem_read(0x62527C, 4) == bytes(4)
        assert calls[-1] == '0x44c61d'
    return dict(item=item, calls=calls)


def main():
    source = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(source).hexdigest() != KNOWN_SHA256:
        raise ValueError('Unknown executable')
    output = [trace(source, item) for item in range(7)]
    expected = {1: '0x40d980', 2: '0x4073a0', 4: '0x404380', 5: '0x4061b0'}
    for item, target in expected.items():
        assert output[item]['calls'] == [target]
    assert not output[0]['calls'] and not output[6]['calls']
    print(json.dumps(dict(source_sha256=KNOWN_SHA256, cases=output,
                          reset_default_matrix_bytes=640,
                          scope='Dispatcher only; all calls stubbed'), indent=2))


if __name__ == '__main__':
    main()
