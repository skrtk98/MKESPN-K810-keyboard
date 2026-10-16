"""Read Windows HID capabilities for K810 collections; sends no reports."""
import ctypes as c
from ctypes import wintypes as w
import json
import struct
import sys

import hid


def main():
    if sys.platform != 'win32':
        raise SystemExit('Windows only')
    kernel = c.WinDLL('kernel32', use_last_error=True)
    api = c.WinDLL('hid', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p,
                                  w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    api.HidD_GetPreparsedData.argtypes = [w.HANDLE, c.POINTER(c.c_void_p)]
    api.HidD_FreePreparsedData.argtypes = [c.c_void_p]
    api.HidP_GetCaps.argtypes = [c.c_void_p, c.c_void_p]
    api.HidP_GetValueCaps.argtypes = [c.c_int, c.c_void_p, c.POINTER(w.USHORT), c.c_void_p]
    api.HidP_GetButtonCaps.argtypes = api.HidP_GetValueCaps.argtypes
    results = []
    for device in hid.enumerate(0x30FA, 0x2350):
        path = device['path'].decode()
        handle = kernel.CreateFileW(path, 0, 3, None, 3, 0, None)
        if handle == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        preparsed = c.c_void_p()
        try:
            if not api.HidD_GetPreparsedData(handle, c.byref(preparsed)):
                raise c.WinError(c.get_last_error())
            caps = c.create_string_buffer(64)
            status = api.HidP_GetCaps(preparsed, caps)
            if status != 0x110000:
                raise RuntimeError(f'HidP_GetCaps status {status:x}')
            fields = struct.unpack('<32H', caps.raw)
            result = dict(usage=fields[0], usage_page=fields[1],
                          input_length=fields[2], output_length=fields[3],
                          feature_length=fields[4], interface=device['interface_number'],
                          capabilities=[])
            for report_type, label, start in ((0, 'input', 23), (1, 'output', 26), (2, 'feature', 29)):
                for delta, kind, function in ((0, 'button', api.HidP_GetButtonCaps),
                                              (1, 'value', api.HidP_GetValueCaps)):
                    count = w.USHORT(fields[start + delta])
                    if not count.value:
                        continue
                    data = c.create_string_buffer(72 * count.value)
                    status = function(report_type, data, c.byref(count), preparsed)
                    if status != 0x110000:
                        raise RuntimeError(f'HidP caps status {status:x}')
                    for index in range(count.value):
                        item = data.raw[index*72:(index+1)*72]
                        capability = dict(type=label, kind=kind,
                            usage_page=struct.unpack_from('<H', item)[0],
                            report_id=item[2], is_range=bool(item[12]),
                            usage_min=struct.unpack_from('<H', item, 56)[0],
                            usage_max=struct.unpack_from('<H', item, 58)[0] if item[12] else None,
                            raw_hex=item.hex())
                        if kind == 'value':
                            capability.update(bit_size=struct.unpack_from('<H', item, 18)[0],
                                              report_count=struct.unpack_from('<H', item, 20)[0])
                        result['capabilities'].append(capability)
            results.append(result)
        finally:
            if preparsed:
                api.HidD_FreePreparsedData(preparsed)
            kernel.CloseHandle(handle)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
