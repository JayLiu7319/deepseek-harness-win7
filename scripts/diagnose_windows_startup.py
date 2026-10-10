"""Read desktop/token context and exercise owned runner fixtures; no desktop ACL edits."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dsh.sandbox import windows_acl


def worker():
    output, mode, flags, explicit = Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), bool(int(sys.argv[5]))
    api = windows_acl.WinApi()
    original_startup = windows_acl.Startup
    original_init = windows_acl.WinApi.__init__

    def init(instance):
        original_init(instance)
        create = instance.CreateRestrictedToken
        def restricted(*args):
            values = list(args)
            values[1] = flags
            return create(*values)
        instance.CreateRestrictedToken = restricted
    windows_acl.WinApi.__init__ = init
    api = windows_acl.WinApi()
    api.kernel.GetCurrentThreadId.restype = w.DWORD
    user = c.WinDLL('user32', use_last_error=True)
    user.GetProcessWindowStation.restype = c.c_void_p
    user.GetThreadDesktop.argtypes = [w.DWORD]
    user.GetThreadDesktop.restype = c.c_void_p
    user.GetUserObjectInformationW.argtypes = [c.c_void_p, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    names = []
    for handle in (user.GetProcessWindowStation(), user.GetThreadDesktop(api.kernel.GetCurrentThreadId())):
        name, needed = c.create_unicode_buffer(512), w.DWORD()
        api.check(user.GetUserObjectInformationW(handle, 2, name, c.sizeof(name), c.byref(needed)), 'GetUserObjectInformation')
        names.append(name.value)
    if explicit:
        def startup():
            value = original_startup()
            value.desktop = '\\'.join(names)
            return value
        windows_acl.Startup = startup
    api.kernel.GetConsoleWindow.restype = c.c_void_p
    api.kernel.GetFileType.argtypes = [c.c_void_p]
    result = dict(mode=mode, flags=flags, explicitDesktop=explicit, desktop=names,
                  console=bool(api.kernel.GetConsoleWindow()), stdinType=api.kernel.GetFileType(api.GetStdHandle(-10)))
    payload_kind = sys.argv[6]
    executable = sys.executable if payload_kind == 'current' else getattr(sys, '_base_executable', sys.executable)
    result.update(payloadKind=payload_kind, executable=executable)
    payload = [executable, '-c', 'print("RESTRICTED_STARTUP_READY",flush=True)']
    if mode == 'api':
        with api.restricted_token([windows_acl.capability_sid(str(output.parent))]) as token:
            result['exitCode'] = api.run(token, payload, str(ROOT))
    else:
        from dsh.sandbox import windows_runner
        fixture = Path(tempfile.mkdtemp(prefix='startup-', dir=str(output.parent)))
        workspace, temp = fixture / 'workspace', fixture / 'temp'
        workspace.mkdir()
        temp.mkdir()
        result['fixture'] = str(fixture)
        result['exitCode'] = windows_runner.main(['--workspace', str(workspace), '--temp', str(temp),
                                                '--mode', 'workspace-write', '--'] + payload)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return 0


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
    worker_output = output.with_name(output.stem + '-workers')
    worker_output.mkdir(exist_ok=False)
    result['redirectedProbes'] = []
    for mode, payload_kind in ((mode, payload_kind) for mode in ('api', 'runner') for payload_kind in ('current', 'base')):
        for flags in (0xd, 0x9):
            for explicit in (False, True):
                for no_window in (False, True):
                    for stdin in ('nul', 'pipe'):
                        name = '{}-{}-{}-{}-{}-{}'.format(mode, payload_kind, flags, int(explicit), int(no_window), stdin)
                        report = worker_output / (name + '.json')
                        command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(report), mode, str(flags), str(int(explicit)), payload_kind]
                        options = dict(cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                                       creationflags=0x08000000 if no_window else 0)
                        if stdin == 'nul':
                            options['stdin'] = subprocess.DEVNULL
                        else:
                            options['input'] = b''
                        completed = subprocess.run(command, **options)
                        (worker_output / (name + '.stdout')).write_bytes(completed.stdout)
                        (worker_output / (name + '.stderr')).write_bytes(completed.stderr)
                        observation = json.loads(report.read_text(encoding='utf-8')) if report.exists() else {}
                        observation.update(parentNoWindow=no_window, parentStdin=stdin, workerExit=completed.returncode)
                        result['redirectedProbes'].append(observation)
                        print(json.dumps(observation), flush=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--worker']:
        sys.exit(worker())
    main()
