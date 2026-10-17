"""Fetch/validate fixed Microsoft offline inputs outside the source repository.

This entry downloads and inspects bytes. System installation belongs to the
explicit installer flow; no prerequisite executable is launched here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).with_name('windows-prerequisite-inputs.json')


def external_directory(directory, root=None):
    directory, root = Path(directory).resolve(), Path(ROOT if root is None else root).resolve()
    try:
        directory.relative_to(root)
    except ValueError:
        return directory
    raise ValueError('Windows prerequisites must be kept outside the Git source directory')


def inputs(architecture):
    if architecture not in ('x86', 'x64', 'both'):
        raise ValueError('Unsupported prerequisite architecture')
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if manifest.get('schema') != 1:
        raise ValueError('Invalid fixed prerequisite manifest')
    rows = [row for row in manifest['inputs'] if architecture == 'both' or row['architecture'] in (architecture, 'x86-x64')]
    expected = {kind + '-' + arch for kind in ('ssu', 'sha2', 'd3d', 'wmf')
                for arch in (('x86', 'x64') if architecture == 'both' else (architecture,))} | {'net472'}
    if {row['id'] for row in rows} != expected or len(rows) != len(expected):
        raise ValueError('Fixed prerequisite set is incomplete or duplicated')
    return rows


def verify_file(filename, record):
    filename = Path(filename)
    if (not filename.is_file() or filename.is_symlink() or
            getattr(filename.lstat(), 'st_reparse_tag', 0) or filename.stat().st_nlink != 1):
        raise ValueError('Prerequisite input missing or aliased: ' + filename.name)
    if filename.stat().st_size != record['bytes']:
        raise ValueError('Prerequisite input size differs: ' + filename.name)
    digest = hashlib.sha256()
    with filename.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != record['sha256']:
        raise ValueError('Prerequisite input SHA256 differs: ' + filename.name)


def validate_prerequisites(directory, architecture):
    directory = external_directory(directory)
    selected = inputs(architecture)
    for row in selected:
        filename = directory / row['filename']
        verify_file(filename, row)
        if 'members' in row:
            with zipfile.ZipFile(str(filename)) as archive:
                expected = {item['filename']: item for item in row['members']}
                if sorted(archive.namelist()) != sorted(expected):
                    raise ValueError('WMF archive member set differs')
                for name, record in expected.items():
                    value = archive.read(name)
                    if len(value) != record['bytes'] or hashlib.sha256(value).hexdigest() != record['sha256']:
                        raise ValueError('WMF archive member bytes differ')
    return selected


def download(directory, architecture):
    directory = external_directory(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for row in inputs(architecture):
        target = directory / row['filename']
        if not target.exists():
            url = urlsplit(row['url'])
            if url.scheme != 'https' or url.hostname not in ('download.microsoft.com', 'catalog.s.download.windowsupdate.com'):
                raise ValueError('Prerequisite URL is not a fixed Microsoft HTTPS source')
            descriptor, temporary = tempfile.mkstemp(prefix='.dsh-download-', dir=str(directory))
            try:
                with os.fdopen(descriptor, 'wb') as stream, urlopen(row['url'], timeout=60) as response:
                    final = urlsplit(response.geturl())
                    if final.scheme != 'https' or final.hostname != url.hostname:
                        raise ValueError('Prerequisite download redirected outside its fixed source')
                    size = 0
                    while True:
                        data = response.read(1024 * 1024)
                        if not data:
                            break
                        size += len(data)
                        if size > row['bytes']:
                            raise ValueError('Prerequisite download exceeds fixed size')
                        stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                verify_file(temporary, row)
                if target.exists():
                    raise ValueError('Prerequisite target appeared during download; preserving it')
                os.rename(temporary, str(target))
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        verify_file(target, row)
        print('Verified ' + row['id'] + ' ' + row['sha256'], flush=True)
    return validate_prerequisites(directory, architecture)


def stage_prerequisites(directory, architecture, destination):
    selected = validate_prerequisites(directory, architecture)
    if architecture not in ('x86', 'x64'):
        raise ValueError('Select exactly one installer architecture')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    staged = []
    for row in selected:
        source = Path(directory) / row['filename']
        if 'members' in row:
            member = next(item for item in row['members'] if item['filename'].lower().endswith('.msu'))
            target = destination / ('wmf-' + architecture + '.msu')
            with zipfile.ZipFile(str(source)) as archive, archive.open(member['filename']) as stream, target.open('xb') as output:
                shutil.copyfileobj(stream, output, 1024 * 1024)
            verify_file(target, member)
        else:
            target = destination / (row['id'] + source.suffix)
            shutil.copyfile(str(source), str(target))
            verify_file(target, row)
        staged.append(dict(id=row['id'],filename=target.name,bytes=target.stat().st_size,
                           sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
    return staged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--architecture', choices=('x86', 'x64', 'both'), default='both')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    selected = (validate_prerequisites if args.verify_only else download)(args.output_dir, args.architecture)
    print(json.dumps(dict(status='verified',inputs=len(selected),installationExecuted=False)))


if __name__ == '__main__':
    main()
