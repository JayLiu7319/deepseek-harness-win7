import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.prepare_x86_runtime import checked_input, extract_wheel
from scripts.ucrt_inputs import bundle_ucrt, verify_pinned_ucrt

ROOT = Path(__file__).resolve().parents[1]


def test_x86_ucrt_bundles_exact_architecture_and_rejects_changed_bytes(tmp_path):
    expected = verify_pinned_ucrt(ROOT, 'x86')
    assert expected['architecture'] == 'x86'
    bundle_ucrt(ROOT, tmp_path, 'x86')
    from scripts.ucrt_inputs import validate_bundled_ucrt
    assert validate_bundled_ucrt(tmp_path, expected) == expected
    (tmp_path / 'ucrtbase.dll').write_bytes(b'foreign architecture or corruption')
    with pytest.raises(ValueError, match='binary changed'):
        validate_bundled_ucrt(tmp_path, expected)


def test_x86_external_input_hash_is_checked_before_consumption(tmp_path):
    payload = tmp_path / 'input.zip'
    payload.write_bytes(b'actual pinned bytes')
    row = dict(name=payload.name, bytes=payload.stat().st_size,
               sha256=hashlib.sha256(payload.read_bytes()).hexdigest())
    assert checked_input(tmp_path, row) == payload
    payload.write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        checked_input(tmp_path, row)


@pytest.mark.parametrize('member', ['../escape.py', '/escape.py', 'C:/escape.py', 'package\\escape.py', 'package.data/purelib/file.py'])
def test_unreviewed_wheel_paths_cannot_escape_or_relocate(tmp_path, member):
    archive = tmp_path / 'fixture.whl'
    with zipfile.ZipFile(str(archive), 'w') as bundle:
        bundle.writestr(member, b'must not publish')
    if chr(92) in member:
        # Windows ZipInfo normalizes separators on write; retain a raw foreign
        # member name in both local and central headers for this rejection.
        archive.write_bytes(archive.read_bytes().replace(member.replace(chr(92), '/').encode('utf-8'), member.encode('utf-8')))
    destination = tmp_path / 'owned'
    destination.mkdir()
    with pytest.raises(ValueError):
        extract_wheel(archive, destination)
    assert list(destination.iterdir()) == []


def test_overlapping_wheels_cannot_replace_another_distribution(tmp_path):
    archive = tmp_path / 'fixture.whl'
    with zipfile.ZipFile(str(archive), 'w') as bundle:
        bundle.writestr('shared.py', b'first')
    destination = tmp_path / 'owned'
    destination.mkdir()
    extract_wheel(archive, destination)
    with zipfile.ZipFile(str(archive), 'w') as bundle:
        bundle.writestr('shared.py', b'second')
    with pytest.raises(ValueError, match='Overlapping'):
        extract_wheel(archive, destination)
    assert (destination / 'shared.py').read_bytes() == b'first'


def test_incompatible_pywinpty_extension_is_excluded_from_runtime_lock():
    from packaging.requirements import Requirement
    current = {Requirement(line).name.lower(): line for line in (ROOT / 'requirements-runtime.lock').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')}
    x86 = {Requirement(line).name.lower(): line for line in (ROOT / 'requirements-runtime-x86.lock').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#')}
    assert x86 == {name: line for name, line in current.items() if name != 'pywinpty'}
    manifest = json.loads((ROOT / 'scripts/x86-inputs.json').read_text(encoding='utf-8'))
    assert [row['name'] for row in manifest['wheels'] if row['resourceOnly']] == ['pywinpty']


@pytest.mark.parametrize('architecture,compiler', [('x64', 'i686-w64-mingw32-clang.exe'), ('x86', 'x86_64-w64-mingw32-clang.exe')])
def test_native_build_cannot_label_the_other_compiler_architecture(tmp_path, architecture, compiler):
    from scripts.build_quickjs import build
    from scripts.build_zstd import checked_inputs
    with pytest.raises(ValueError, match='compiler architecture differs'):
        build(tmp_path, tmp_path / compiler, tmp_path / 'output', architecture)
    with pytest.raises(ValueError, match='compiler architecture differs'):
        checked_inputs(tmp_path, tmp_path / compiler, architecture)
    assert not (tmp_path / 'output').exists()


def test_ripgrep_architectures_keep_separate_pinned_bytes():
    from scripts.build_portable import resolve_pinned_ripgrep_source, verify_pinned_ripgrep
    x86 = resolve_pinned_ripgrep_source(ROOT, 'x86')
    assert verify_pinned_ripgrep(ROOT, x86, 'x86')[1]['target'] == 'i686-pc-windows-msvc'
    with pytest.raises(ValueError, match='exact pinned ripgrep'):
        verify_pinned_ripgrep(ROOT, x86, 'x64')
    x64 = resolve_pinned_ripgrep_source(ROOT, 'x64')
    with pytest.raises(ValueError, match='exact pinned ripgrep'):
        verify_pinned_ripgrep(ROOT, x64, 'x86')


def test_x86_build_requires_explicit_inputs_and_cannot_replace_default_portable():
    from scripts.build_portable import build_portable
    with pytest.raises(ValueError, match='requires explicit'):
        build_portable(architecture='x86')


def test_portable_probe_rejects_unknown_architecture_before_creating_workspace(tmp_path):
    import subprocess
    import sys
    workspace = tmp_path / 'workspace'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/portable_runtime_probe.py'),
                             '--architecture', 'arm64', '--workspace', str(workspace)],
                            capture_output=True, encoding='utf-8', timeout=10)
    assert result.returncode == 2 and 'invalid choice' in result.stderr
    assert not workspace.exists()
