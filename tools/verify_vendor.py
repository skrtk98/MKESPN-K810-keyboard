"""Emulate ONLY the decoded pure x86 routines. No vendor native code/DLL runs.

Usage: uv run --group research python tools/verify_vendor.py PATH_TO_EXE
The PE is mapped as bytes inside Unicorn. HID/Sleep are intercepted; other calls
are rejected. Regenerate tests/vendor_vectors.json from the known app hash.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys

import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_EAX, UC_X86_REG_EBP, UC_X86_REG_ESP, UC_X86_REG_EIP

KNOWN_SHA256 = "ef79b5e0ad1786dd682bc8ed1dad4626627c0518639ec67a702088d6322b8e36"


def emulate(executable, routine, address, data):
    pe = pefile.PE(data=executable)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.mem_map(0x2000000, 0x1000)
    vm.mem_write(0x5BE478, struct.pack('<I', 0x2000100))
    vm.mem_write(0x624EF0, struct.pack('<H', 8))
    vm.mem_write(0x63DDA8, bytes(4))  # BSS zero / ordinary K201 branch
    vm.mem_write(0x1001000, data)
    vm.mem_write(0x1010000, struct.pack('<4I', 0x2000000, address, 0x1001000, len(data)))
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    trace = []
    read_count = 0

    def return_stdcall(size):
        sp = vm.reg_read(UC_X86_REG_ESP)
        target = struct.unpack('<I', vm.mem_read(sp, 4))[0]
        vm.reg_write(UC_X86_REG_ESP, sp + 4 + size)
        vm.reg_write(UC_X86_REG_EIP, target)
        vm.reg_write(UC_X86_REG_EAX, 1)

    def hook(uc, ip, size, user):
        nonlocal read_count
        if ip == 0x2000000:
            uc.emu_stop()
        elif ip == 0x2000100:
            return_stdcall(4)
        elif ip in (0x58F379, 0x58F373):
            sp = uc.reg_read(UC_X86_REG_ESP)
            _, handle, buffer, length = struct.unpack('<4I', uc.mem_read(sp, 16))
            if ip == 0x58F379:
                trace.append({"set": bytes(uc.mem_read(buffer, length)).hex()})
            else:
                trace.append({"get": length})
                uc.mem_write(buffer + 1, bytes([data[read_count]]))
                read_count += 1
            return_stdcall(12)
        elif not (routine <= ip <= (0x407331 if routine == 0x4071D0 else 0x4071C8)):
            raise RuntimeError(f"Unexpected code target 0x{ip:x}")

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(routine, 0x2000001, count=10000)
    if vm.reg_read(UC_X86_REG_EIP) != 0x2000000:
        raise RuntimeError("Emulation did not return normally")
    return trace


def emulate_table(executable):
    pe = pefile.PE(data=executable)
    vm = Uc(UC_ARCH_X86, UC_MODE_32)
    vm.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
    vm.mem_write(0x400000, pe.get_memory_mapped_image())
    vm.mem_map(0x1000000, 0x20000)
    vm.reg_write(UC_X86_REG_ESP, 0x1010000)
    vm.reg_write(UC_X86_REG_EBP, 0x1011000)
    vm.mem_write(0x1011000 - 0xC64, struct.pack('<I', 0x128))
    vm.mem_write(0x63CF98, struct.pack('<160I', *range(160)))
    blocks = []

    def hook(uc, ip, size, user):
        if ip == 0x411134:
            uc.emu_stop()
        elif ip == 0x4071D0:
            sp = uc.reg_read(UC_X86_REG_ESP)
            target, address, buffer, length = struct.unpack('<4I', uc.mem_read(sp, 16))
            blocks.append({"address": address, "data": bytes(uc.mem_read(buffer, length)).hex()})
            uc.reg_write(UC_X86_REG_ESP, sp + 16)
            uc.reg_write(UC_X86_REG_EIP, target)
        elif not 0x411021 <= ip < 0x411134:
            raise RuntimeError(f"Unexpected table code target 0x{ip:x}")

    vm.hook_add(UC_HOOK_CODE, hook)
    vm.emu_start(0x411021, 0x411135, count=10000)
    if len(blocks) != 20:
        raise RuntimeError("Table serializer did not produce 20 blocks")
    return blocks


if __name__ == '__main__':
    executable = Path(sys.argv[1]).read_bytes()
    if hashlib.sha256(executable).hexdigest() != KNOWN_SHA256:
        raise SystemExit("Unknown binary; refusing to apply these address assumptions")
    data = bytes.fromhex("14 00 00 00 00 00 00 00")
    vectors = {"source_sha256": KNOWN_SHA256, "address": 0x128, "data": data.hex(),
               "write": emulate(executable, 0x4071D0, 0x128, data),
               "read": emulate(executable, 0x406FD0, 0x128, data),
               "table": emulate_table(executable)}
    output = Path('tests/vendor_vectors.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(vectors, indent=2) + '\n', encoding='utf8')
    print(f"Verified vendor read/write routines and table serializer: {output}")
