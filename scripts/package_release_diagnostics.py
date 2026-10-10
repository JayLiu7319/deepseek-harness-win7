"""Preserve release observations without traversing pytest's opaque links."""
import argparse
import ctypes
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import xml.etree.ElementTree as ET
import zipfile


MANIFEST = '_diagnostics_inventory.json'


def native(path):
    absolute = os.path.abspath(str(path))
    if os.name != 'nt' or absolute.startswith('\\\\?\\'):
        return absolute
    return '\\\\?\\UNC\\' + absolute[2:] if absolute.startswith('\\\\') else '\\\\?\\' + absolute


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns


def raw_reparse(path):
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p,
                                      wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                      ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.DeviceIoControl.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    # OPEN_REPARSE_POINT | BACKUP_SEMANTICS: inspect the link itself.
    handle = kernel.CreateFileW(path, 0, 7, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        buffer = ctypes.create_string_buffer(16384)
        returned = wintypes.DWORD()
        if not kernel.DeviceIoControl(handle, 0x000900A8, None, 0, buffer,
                                      len(buffer), ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.raw[:returned.value].hex()
    finally:
        kernel.CloseHandle(handle)


def write_inventory(archive, manifest):
    # Stream large inventories instead of creating another complete JSON copy.
    with archive.open(MANIFEST, 'w', force_zip64=True) as output:
        with io.TextIOWrapper(output, encoding='utf-8') as text:
            json.dump(manifest, text, indent=2)
            text.write('\n')


def print_summary(source, stream=None):
    """Keep primary failures readable even if archive/upload subsequently fails."""
    stream = stream or sys.stdout
    source = Path(source)
    if linked(os.lstat(native(source))) or os.path.normcase(os.path.abspath(str(source))) != os.path.normcase(os.path.realpath(str(source))):
        raise ValueError('Linked diagnostics root is refused')
    summary = source / 'summary.json'
    if summary.is_file() and not linked(os.lstat(native(summary))):
        try:
            print('Gate summary: ' + summary.read_text(encoding='utf-8')[:32768], file=stream, flush=True)
        except (OSError, UnicodeError) as error:
            print('Gate summary unreadable: ' + str(error), file=stream, flush=True)
    report = source / 'pytest.xml'
    if not report.is_file() or linked(os.lstat(native(report))):
        print('Regression XML unavailable; no final test counts inferred.', file=stream, flush=True)
        return
    try:
        cases = list(ET.parse(str(report)).getroot().iter('testcase'))
    except (ET.ParseError, OSError) as error:
        print('Regression XML unreadable; no final test counts inferred: ' + str(error), file=stream, flush=True)
        return
    failures = [(case, child) for case in cases for child in case if child.tag in ('failure', 'error')]
    skipped = sum(case.find('skipped') is not None for case in cases)
    print(json.dumps(dict(collected=len(cases), failed_or_error=len(failures), skipped=skipped)),
          file=stream, flush=True)
    for case, failure in failures[:20]:
        print('REGRESSION ' + failure.tag + ': ' + case.get('classname', '') + '::' + case.get('name', ''),
              file=stream, flush=True)
        print((failure.text or failure.get('message', ''))[:8192], file=stream, flush=True)
    if len(failures) > 20:
        print('Further failures remain in the original XML and diagnostics carrier.', file=stream, flush=True)


def package(source, destination):
    source = Path(os.path.abspath(str(source)))
    destination = Path(os.path.abspath(str(destination)))
    if os.path.normcase(str(source)) != os.path.normcase(os.path.realpath(str(source))):
        raise ValueError('Linked diagnostics root is refused')
    root = native(source)
    initial = os.lstat(root)
    if linked(initial) or not stat.S_ISDIR(initial.st_mode):
        raise ValueError('Real diagnostics directory required')
    try:
        destination.relative_to(source)
    except ValueError:
        pass
    else:
        raise ValueError('Diagnostics archive must be outside its source')
    if os.path.normcase(str(destination.parent)) != os.path.normcase(os.path.realpath(str(destination.parent))):
        raise ValueError('Linked diagnostics destination is refused')
    partial = Path(str(destination) + '.partial')
    if os.path.lexists(str(destination)) or os.path.lexists(str(partial)):
        raise FileExistsError('Fresh diagnostics archive required')
    rows = []
    with zipfile.ZipFile(str(partial), 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        stack = [(root, '')]
        while stack:
            folder, prefix = stack.pop()
            before = os.lstat(folder)
            if linked(before) or not stat.S_ISDIR(before.st_mode):
                raise ValueError('Diagnostics directory changed during traversal')
            with os.scandir(folder) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
            for entry in children:
                name = prefix + entry.name
                if name == MANIFEST:
                    raise ValueError('Reserved diagnostics inventory name already exists')
                info = os.lstat(entry.path)
                row = dict(path=name, mode=info.st_mode, bytes=info.st_size,
                           links=info.st_nlink, attributes=getattr(info, 'st_file_attributes', 0))
                if linked(info):
                    row['kind'] = 'opaque-link'
                    if os.name == 'nt':
                        row['reparseHex'] = raw_reparse(entry.path)
                    else:
                        row['target'] = os.readlink(entry.path)
                    if identity(os.lstat(entry.path)) != identity(info):
                        raise ValueError('Diagnostics link changed')
                elif stat.S_ISDIR(info.st_mode):
                    row['kind'] = 'directory'
                    archive.writestr(name + '/', b'')
                    stack.append((entry.path, name + '/'))
                elif stat.S_ISREG(info.st_mode):
                    row['kind'] = 'file'
                    sha = hashlib.sha256()
                    with open(entry.path, 'rb') as stream:
                        if identity(os.fstat(stream.fileno())) != identity(info):
                            raise ValueError('Diagnostics file changed before reading')
                        with archive.open(name, 'w', force_zip64=True) as output:
                            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                                output.write(chunk)
                                sha.update(chunk)
                        del output
                        if identity(os.fstat(stream.fileno())) != identity(info):
                            raise ValueError('Diagnostics file changed during reading')
                    if linked(os.lstat(entry.path)) or identity(os.lstat(entry.path)) != identity(info):
                        raise ValueError('Diagnostics file changed after reading')
                    row['sha256'] = sha.hexdigest()
                else:
                    raise ValueError('Unsupported diagnostics file: ' + name)
                rows.append(row)
            if identity(os.lstat(folder)) != identity(before):
                raise ValueError('Diagnostics directory changed during enumeration')
        manifest = dict(format='dsh-release-diagnostics@1', source=str(source), members=rows,
                        scope='Regular bytes retained; links recorded without following targets; no source cleanup.')
        write_inventory(archive, manifest)
    del archive
    if identity(os.lstat(root)) != identity(initial):
        raise ValueError('Diagnostics root changed')
    with zipfile.ZipFile(str(partial)) as archive:
        if archive.testzip() is not None:
            raise ValueError('Diagnostics ZIP CRC failed')
    if os.path.lexists(str(destination)):
        raise FileExistsError('Diagnostics destination appeared')
    partial.rename(destination)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    args = parser.parse_args(argv)
    print_summary(args.source)
    manifest = package(args.source, args.archive)
    print(json.dumps(dict(archive=str(args.archive), files=sum(row['kind'] == 'file' for row in manifest['members']),
                          opaque_links=sum(row['kind'] == 'opaque-link' for row in manifest['members']))), flush=True)
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
