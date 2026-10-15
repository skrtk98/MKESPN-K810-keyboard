"""Windows Raw Input observer, restricted to K810 device paths.

No synthesized input, HID configuration writes, or capture of other keyboards.
API reference: https://learn.microsoft.com/en-us/windows/win32/inputdev/raw-input
"""
import argparse
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import struct
import sys
import time


def main():
    if sys.platform!='win32':raise SystemExit('Windows only')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=180)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stop-file',type=Path,help='Stop cleanly when this file appears')
    args=parser.parse_args()
    if not 1<=args.seconds<=600:raise SystemExit('Duration must be 1..600 seconds')
    user=c.WinDLL('user32',use_last_error=True);kernel=c.WinDLL('kernel32',use_last_error=True)
    LRESULT=c.c_ssize_t;WPARAM=c.c_size_t;LPARAM=c.c_ssize_t
    proc_type=c.WINFUNCTYPE(LRESULT,w.HWND,w.UINT,WPARAM,LPARAM)
    class WindowClass(c.Structure):
        _fields_=[('style',w.UINT),('proc',proc_type),('extra',c.c_int),('window_extra',c.c_int),
                  ('instance',w.HINSTANCE),('icon',w.HICON),('cursor',w.HANDLE),('brush',w.HBRUSH),
                  ('menu',w.LPCWSTR),('name',w.LPCWSTR)]
    class Device(c.Structure):
        _fields_=[('page',w.USHORT),('usage',w.USHORT),('flags',w.DWORD),('target',w.HWND)]
    class Header(c.Structure):
        _fields_=[('kind',w.DWORD),('size',w.DWORD),('device',w.HANDLE),('param',WPARAM)]
    user.DefWindowProcW.argtypes=[w.HWND,w.UINT,WPARAM,LPARAM];user.DefWindowProcW.restype=LRESULT
    user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,c.c_int,c.c_int,c.c_int,c.c_int,w.HWND,w.HMENU,w.HINSTANCE,c.c_void_p]
    user.CreateWindowExW.restype=w.HWND
    user.GetRawInputDeviceInfoW.argtypes=[w.HANDLE,w.UINT,c.c_void_p,c.POINTER(w.UINT)]
    user.GetRawInputData.argtypes=[w.HANDLE,w.UINT,c.c_void_p,c.POINTER(w.UINT),w.UINT]
    user.RegisterRawInputDevices.argtypes=[c.POINTER(Device),w.UINT,w.UINT]
    user.RegisterClassW.argtypes=[c.POINTER(WindowClass)]
    user.PeekMessageW.argtypes=[c.POINTER(w.MSG),w.HWND,w.UINT,w.UINT,w.UINT]
    user.TranslateMessage.argtypes=[c.POINTER(w.MSG)];user.DispatchMessageW.argtypes=[c.POINTER(w.MSG)];user.DispatchMessageW.restype=LRESULT
    user.DestroyWindow.argtypes=[w.HWND]
    kernel.GetModuleHandleW.argtypes=[w.LPCWSTR];kernel.GetModuleHandleW.restype=w.HMODULE
    events=[];names={};started=time.monotonic()

    def device_name(handle):
        if handle not in names:
            size=w.UINT();user.GetRawInputDeviceInfoW(handle,0x20000007,None,c.byref(size))
            buf=c.create_unicode_buffer(size.value+1)
            user.GetRawInputDeviceInfoW(handle,0x20000007,buf,c.byref(size))
            names[handle]=buf.value
        return names[handle]

    @proc_type
    def callback(hwnd,msg,wp,lp):
        if msg==0xff:
            size=w.UINT();user.GetRawInputData(lp,0x10000003,None,c.byref(size),c.sizeof(Header))
            if size.value:
                buf=c.create_string_buffer(size.value)
                user.GetRawInputData(lp,0x10000003,buf,c.byref(size),c.sizeof(Header))
                header=Header.from_buffer(buf);name=device_name(header.device)
                if 'VID_30FA&PID_2350' in name.upper():
                    raw=buf.raw[c.sizeof(Header):size.value]
                    event=dict(seconds=round(time.monotonic()-started,3),kind=header.kind,device=name,data_hex=raw.hex())
                    if header.kind==0 and len(raw)>=24:
                        buttons,button_data=struct.unpack_from('<HH',raw,4)
                        event.update(buttons=buttons,wheel=struct.unpack('<h',struct.pack('<H',button_data))[0],x=struct.unpack_from('<i',raw,12)[0],y=struct.unpack_from('<i',raw,16)[0])
                    elif header.kind==1 and len(raw)>=16:
                        scan,flags,_,vk,message,_extra=struct.unpack_from('<HHHHII',raw)
                        event.update(scan=scan,flags=flags,vk=vk,message=message)
                    events.append(event);print(json.dumps(event),flush=True)
        return user.DefWindowProcW(hwnd,msg,wp,lp)

    instance=kernel.GetModuleHandleW(None);name='K810ReadOnlyInputObserver'
    cls=WindowClass(0,callback,0,0,instance,None,None,None,None,name)
    if not user.RegisterClassW(c.byref(cls)):raise c.WinError(c.get_last_error())
    hwnd=user.CreateWindowExW(0,name,'',0,0,0,0,0,w.HWND(-3),None,instance,None)
    if not hwnd:raise c.WinError(c.get_last_error())
    devices=(Device*4)(Device(1,2,0x100,hwnd),Device(1,6,0x100,hwnd),Device(12,1,0x100,hwnd),Device(1,128,0x100,hwnd))
    if not user.RegisterRawInputDevices(devices,len(devices),c.sizeof(Device)):raise c.WinError(c.get_last_error())
    print('READY: observing only K810 input; ordinary input remains enabled.',flush=True)
    message=w.MSG()
    try:
        checkpoint=started
        while time.monotonic()-started<args.seconds and not (args.stop_file and args.stop_file.exists()):
            while user.PeekMessageW(c.byref(message),None,0,0,1):
                user.TranslateMessage(c.byref(message));user.DispatchMessageW(c.byref(message))
            if time.monotonic()-checkpoint>=1:
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps(dict(events=events),indent=2),encoding='utf8')
                checkpoint=time.monotonic()
            time.sleep(.005)
    finally:
        user.DestroyWindow(hwnd)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(dict(events=events),indent=2),encoding='utf8')
        print(f'Saved {len(events)} K810 events to {args.output}',flush=True)


if __name__=='__main__':main()
