"""Desktop plugin transactions reuse the profile-owned Python installer."""
import argparse
import json
import os
from pathlib import Path

from dsh.boot.profile import read_profile_manifest
from dsh.boot.profile_boot import INSTALL_ANCHOR
from dsh.boot.python_plugins import install, uninstall, validate_package, copy_source
from dsh.boot.python_plugin_versions import upgrade, rollback


def list_plugins(directory):
    manifest = read_profile_manifest('dsh desktop', directory)
    return [dict(name=name, version=record['version']) for name, record in
            manifest.get('dsh', {}).get('pythonPlugins', {}).items()]


def mutate(directory, operation, value, expected_name=None):
    if operation == 'remove':
        uninstall(directory, value)
        return value
    if operation == 'rollback':
        return rollback(directory, value)
    if operation not in ('add', 'upgrade'):
        raise ValueError('Unknown Desktop plugin operation')
    source = Path(value).resolve()
    if not source.exists():
        raise ValueError('Choose an existing Python plugin folder or ZIP package')
    if operation == 'upgrade':
        # Verify the named upgrade before publishing any profile mutation.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='dsh-desktop-package-') as temporary:
            copy_source(str(source), temporary)
            manifest = validate_package(temporary)
            if manifest['name'] != expected_name:
                raise ValueError('Upgrade package name differs from the selected plugin')
    return (install if operation == 'add' else upgrade)(directory, str(source), INSTALL_ANCHOR)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-dir', required=True)
    parser.add_argument('--home', required=True)
    parser.add_argument('--operation', choices=('list', 'add', 'remove', 'upgrade', 'commit', 'recover'), required=True)
    parser.add_argument('--value')
    parser.add_argument('--name')
    args = parser.parse_args()
    os.environ['DSH_HOME'] = str(Path(args.home).resolve())
    from dsh.host.desktop import health_transaction as health
    if args.operation == 'list':
        value = list_plugins(args.profile_dir)
    elif args.operation in ('commit', 'recover'):
        value = getattr(health, args.operation)(args.profile_dir)
    else:
        value = health.prepare(args.profile_dir, args.operation, args.value, args.name)
    print(json.dumps(value, ensure_ascii=True))


if __name__ == '__main__':
    main()
