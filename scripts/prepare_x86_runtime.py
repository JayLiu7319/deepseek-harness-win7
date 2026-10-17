"""Prepare the pinned Win32 CPython runtime and compatible locked wheels."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ucrt_inputs import bundle_ucrt


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_input(directory, row, download=False):
    name = row.get('filename', row.get('name'))
    if Path(name).name != name or '/' in name or chr(92) in name:
        raise ValueError('Invalid x86 input filename')
    target = directory / name
    if download and not target.exists():
        if not row['url'].startswith('https://'):
            raise ValueError('x86 inputs require HTTPS')
        with urllib.request.urlopen(row['url'], timeout=60) as incoming, target.open('xb') as output:
            while True:
                chunk = incoming.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    if target.is_symlink() or not target.is_file() or target.stat().st_nlink != 1:
        raise ValueError('Missing or aliased x86 input: ' + name)
    if target.stat().st_size != row['bytes'] or digest(target) != row['sha256']:
        raise ValueError('Pinned x86 input differs: ' + name)
    return target


def extract_wheel(archive, destination):
    with zipfile.ZipFile(str(archive)) as bundle:
        for entry in bundle.infolist():
            relative = Path(entry.filename)
            if relative.anchor or '..' in relative.parts or ':' in entry.filename or chr(92) in entry.orig_filename:
                raise ValueError('Invalid wheel member')
            if entry.is_dir():
                continue
            if any(part.endswith('.data') for part in relative.parts):
                raise ValueError('Unreviewed wheel relocation')
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = bundle.read(entry)
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError('Overlapping wheel bytes differ')
            else:
                target.write_bytes(data)


def prepare(inputs, stdlib_runtime, output, download=False):
    inputs, stdlib_runtime, output = inputs.resolve(), stdlib_runtime.resolve(), output.absolute()
    if output.exists() or output.resolve() != output:
        raise ValueError('x86 runtime output must be a fresh plain directory')
    for source in (inputs, stdlib_runtime):
        try:
            common = Path(os.path.commonpath([str(output), str(source)]))
        except ValueError:
            continue
        if common == output or common == source:
            raise ValueError('x86 runtime output overlaps an input')
    manifest = json.loads((ROOT / 'scripts/x86-inputs.json').read_text(encoding='utf-8'))
    python_row = next(row for row in manifest['downloads'] if row['name'] == 'python-3.8.10-embed-win32.zip')
    if download:
        inputs.mkdir(parents=True, exist_ok=True)
        (inputs / 'wheels').mkdir(exist_ok=True)
    python_zip = checked_input(inputs, python_row, download)
    wheels = [(row, checked_input(inputs / 'wheels', row, download)) for row in manifest['wheels'] if not row['resourceOnly']]
    observed = subprocess.check_output([str(stdlib_runtime / 'python.exe'), '-I', '-c',
        'import sys;print(".".join(map(str,sys.version_info[:3])))'], encoding='utf-8', timeout=30).strip()
    if observed != '3.8.10' or not (stdlib_runtime / 'Lib/os.py').is_file():
        raise ValueError('Standard library source must be actual CPython 3.8.10')
    output.mkdir(parents=True)
    (output / 'DLLs').mkdir()
    with zipfile.ZipFile(str(python_zip)) as bundle:
        for entry in bundle.infolist():
            name = entry.filename
            if Path(name).name != name or '/' in name or chr(92) in name or ':' in name:
                raise ValueError('Invalid CPython embed member')
            if name.endswith(('.exe', '.dll', '.pyd')) or name == 'LICENSE.txt':
                target = output / ('DLLs/' + name if name.endswith('.pyd') else name)
                target.write_bytes(bundle.read(entry))
    shutil.copytree(str(stdlib_runtime / 'Lib'), str(output / 'Lib'),
                    ignore=shutil.ignore_patterns('site-packages', '__pycache__', 'test', 'tests'))
    (output / 'python38._pth').write_text('.\nLib\nDLLs\nimport site\n', encoding='utf-8')
    bundle_ucrt(ROOT, output, 'x86')
    packages = output / 'Lib/site-packages'
    packages.mkdir()
    for row, archive in wheels:
        extract_wheel(archive, packages)
    command = [str(output / 'python.exe'), '-I', '-c',
        'import json,sys,struct,ssl,sqlite3,yaml;from PIL import Image;'
        'print(json.dumps(dict(version=list(sys.version_info[:3]),bits=struct.calcsize("P")*8,platform=sys.platform)))']
    completed = subprocess.run(command, capture_output=True, timeout=30)
    (output / 'prepare-startup.log').write_bytes(completed.stdout + completed.stderr)
    if completed.returncode or json.loads(completed.stdout) != dict(version=[3, 8, 10], bits=32, platform='win32'):
        raise RuntimeError('Actual x86 runtime startup rejected; preserve prepare-startup.log')
    record = dict(schemaVersion=1, architecture='x86', python=python_row,
                  wheels=[row for row, archive in wheels],
                  stdlibSource=str(stdlib_runtime),
                  stdlibFiles={p.relative_to(output / 'Lib').as_posix(): digest(p)
                               for p in (output / 'Lib').rglob('*') if p.is_file() and 'site-packages' not in p.parts and '__pycache__' not in p.parts},
                  status='prepared', scope='Actual current-Windows x86 execution; no physical Win7 certification.')
    (output / 'prepare-provenance.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs-dir', type=Path, required=True)
    parser.add_argument('--stdlib-runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    record = prepare(args.inputs_dir, args.stdlib_runtime, args.output, args.download)
    print(json.dumps(dict(status=record['status'], architecture=record['architecture'], wheels=len(record['wheels']))))


if __name__ == '__main__':
    main()
