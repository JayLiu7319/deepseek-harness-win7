"""Build a separate offline Windows upgrade ZIP from fixed external inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.windows_prerequisites import stage_prerequisites, validate_prerequisites
from scripts.build_desktop import digest, plain_tree


def build(directory, output, architecture='both'):
    if architecture not in ('x86', 'x64', 'both'):
        raise ValueError('Unsupported upgrade architecture')
    validate_prerequisites(directory, architecture)
    output = Path(output).absolute()
    if output.exists() or output.resolve() != output:
        raise ValueError('Offline upgrade output must be fresh and unlinked')
    if any(output == ROOT / name or ROOT / name in output.parents or output in (ROOT / name).parents
           for name in ('dsh','apps','packages','scripts','reference')):
        raise ValueError('Offline upgrade output overlaps source')
    output.mkdir(parents=True)
    report = dict(schema=1, status='building', architecture=architecture, installationExecuted=False)
    rows = {}
    staged = []
    try:
        for arch in (('x86','x64') if architecture == 'both' else (architecture,)):
            stage = output / ('staged-' + arch)
            records = stage_prerequisites(directory, arch, stage)
            plain_tree(stage)
            for record in records:
                path = stage / record['filename']
                name = 'prerequisites/' + path.name
                identity = dict(bytes=path.stat().st_size, sha256=digest(path))
                if identity != dict(bytes=record['bytes'], sha256=record['sha256']):
                    raise ValueError('Staged upgrade bytes changed')
                if name in rows and rows[name][1] != identity:
                    raise ValueError('Conflicting shared upgrade input')
                rows[name] = (path, identity)
                staged.append((path, identity))
        for name in ('prerequisites.ps1','upgrade-win7.ps1','upgrade-win7.bat'):
            path = ROOT / 'apps/desktop/installer' / name
            rows[name] = (path, dict(bytes=path.stat().st_size, sha256=digest(path)))
        for name, path in [('win7-setup.html', ROOT / 'apps/desktop/win7-setup.html'),
                           ('microsoft-inputs.json', ROOT / 'scripts/windows-prerequisite-inputs.json')]:
            rows[name] = (path, dict(bytes=path.stat().st_size, sha256=digest(path)))
        archive = output / 'dsh-win7-offline-upgrade.zip'
        with zipfile.ZipFile(str(archive), 'x', compression=zipfile.ZIP_STORED) as stream:
            for name, (path, identity) in sorted(rows.items()):
                if digest(path) != identity['sha256']:
                    raise ValueError('Upgrade input changed before archiving')
                stream.write(str(path), name)
        # Verify each actual member before pruning only our reconstructible copies.
        with zipfile.ZipFile(str(archive)) as stream:
            if set(stream.namelist()) != set(rows) or stream.testzip() is not None:
                raise ValueError('Offline upgrade archive members differ')
            for name, (_, identity) in rows.items():
                hasher = hashlib.sha256()
                with stream.open(name) as source:
                    for data in iter(lambda: source.read(1024*1024), b''):
                        hasher.update(data)
                if hasher.hexdigest() != identity['sha256']:
                    raise ValueError('Offline upgrade archive bytes differ')
        report.update(status='built', artifact=dict(path=archive.name,bytes=archive.stat().st_size,sha256=digest(archive)),
                      members=[dict(path=name, **row[1]) for name,row in sorted(rows.items())])
        for path, identity in staged:
            if digest(path) != identity['sha256']:
                raise ValueError('Staged copy changed before cleanup')
        removed = 0
        for path, identity in staged:
            path.unlink()
            removed += identity['bytes']
        for parent in sorted({path.parent for path, _ in staged}):
            parent.rmdir()
        report['cleanup'] = dict(stagedCopies=len(staged), bytes=removed, archiveVerified=True)
        return report
    except BaseException as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (output / 'offline-upgrade-build.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--external-prereq-dir',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--architecture',choices=('x86','x64','both'),default='both')
    args = parser.parse_args()
    print(json.dumps(build(args.external_prereq_dir,args.output_dir,args.architecture),indent=2))


if __name__ == '__main__':
    main()
