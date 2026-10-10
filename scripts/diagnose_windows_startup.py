"""Read desktop/token context and compare explicit desktop startup; no ACL edits."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dsh.sandbox import windows_acl


def main():
    api = windows_acl.WinApi()
    user = c.WinDLL('user32', use_last_error=True)
    user.GetProcessWindowStation.restype = c.c_void_p
    user.GetThreadDesktop.argtypes = [w.DWORD]
    user.GetThreadDesktop.restype = c.c_void_p
    api.kernel.GetCurrentThreadId.restype = w.DWORD
    user.GetUserObjectInformationW.argtypes = [c.c_void_p, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    user.GetUserObjectSecurity.argtypes = [c.c_void_p, c.POINTER(w.DWORD), c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    convert = api.advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    convert.argtypes = [c.c_void_p, w.DWORD, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)]
    result = dict(objects=[], probes=[])
    for kind, handle in [('station', user.GetProcessWindowStation()), ('desktop', user.GetThreadDesktop(api.kernel.GetCurrentThreadId()))]:
        name = c.create_unicode_buffer(512)
        size = w.DWORD()
        api.check(user.GetUserObjectInformationW(handle, 2, name, c.sizeof(name), c.byref(size)), 'GetUserObjectInformation')
        flags, needed = w.DWORD(4), w.DWORD()
        user.GetUserObjectSecurity(handle, c.byref(flags), None, 0, c.byref(needed))
        buffer = c.create_string_buffer(needed.value)
        api.check(user.GetUserObjectSecurity(handle, c.byref(flags), buffer, needed, c.byref(needed)), 'GetUserObjectSecurity')
        text = c.c_void_p()
        api.check(convert(buffer, 1, 4, c.byref(text), None), 'ConvertSecurityDescriptor')
        try:
            result['objects'].append(dict(kind=kind, name=name.value, dacl=c.wstring_at(text)))
        finally:
            api.LocalFree(text)
    desktop = result['objects'][0]['name'] + '\\' + result['objects'][1]['name']
    original_startup = windows_acl.Startup
    original_create = api.CreateRestrictedToken
    for flags in (0xd, 0x9, 0x5):
        def create(*args):
            values = list(args)
            values[1] = flags
            return original_create(*values)
        api.CreateRestrictedToken = create
        for explicit in (False, True):
            def startup():
                value = original_startup()
                if explicit:
                    value.desktop = desktop
                return value
            windows_acl.Startup = startup
            with api.restricted_token([]) as token:
                code = api.run(token, [sys.executable, '-c', 'print("RESTRICTED_STARTUP_READY",flush=True)'], str(ROOT))
            result['probes'].append(dict(flags=flags, explicitDesktop=explicit, exitCode=code))
            print(json.dumps(result['probes'][-1]), flush=True)
    windows_acl.Startup = original_startup
    output = Path(sys.argv[1])
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
