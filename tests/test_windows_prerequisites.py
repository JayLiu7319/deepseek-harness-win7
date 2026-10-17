import hashlib
import io
import zipfile

import pytest

from scripts import windows_prerequisites as prereq


@pytest.fixture(autouse=True)
def isolated_source_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(prereq, 'ROOT', tmp_path / 'source')


def record(name, data, **extra):
    return dict(filename=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), **extra)


@pytest.fixture
def offline_inputs(tmp_path, monkeypatch):
    directory = tmp_path / 'external'
    directory.mkdir()
    payload = b'fixed Microsoft MSU bytes'
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr('WMF.msu', payload)
    rows = [record('wmf.zip', archive.getvalue(), id='wmf-x64', architecture='x64',
                   members=[record('WMF.msu', payload)]),
            record('net.exe', b'offline executable', id='net472', architecture='x86-x64')]
    for row in rows:
        (directory / row['filename']).write_bytes(archive.getvalue() if row['id'].startswith('wmf') else b'offline executable')
    monkeypatch.setattr(prereq, 'inputs', lambda architecture: rows)
    return directory, rows


def test_fixed_manifest_selects_complete_architecture_sets():
    assert len(prereq.inputs('both')) == 9
    for arch in ('x86', 'x64'):
        rows = prereq.inputs(arch)
        assert len(rows) == 5
        assert all(row['architecture'] in (arch, 'x86-x64') for row in rows)
    with pytest.raises(ValueError):
        prereq.inputs('arm64')


def test_prerequisites_cannot_be_stored_inside_source():
    with pytest.raises(ValueError, match='outside'):
        prereq.external_directory(prereq.ROOT / 'dist' / 'prerequisites')


def test_corrupted_existing_download_is_preserved(offline_inputs, monkeypatch):
    directory, rows = offline_inputs
    target = directory / rows[0]['filename']
    corrupted = bytes([target.read_bytes()[0] ^ 1]) + target.read_bytes()[1:]
    target.write_bytes(corrupted)
    monkeypatch.setattr(prereq, 'urlopen', lambda *args, **kwargs: pytest.fail('Existing corruption must not be overwritten'))
    with pytest.raises(ValueError, match='SHA256'):
        prereq.download(directory, 'x64')
    assert target.read_bytes() == corrupted


def test_staging_extracts_only_verified_msu_and_preserves_inputs(offline_inputs, tmp_path):
    directory, rows = offline_inputs
    destination = tmp_path / 'staged'
    result = prereq.stage_prerequisites(directory, 'x64', destination)
    assert {item['filename'] for item in result} == {'wmf-x64.msu', 'net472.exe'}
    assert (destination / 'wmf-x64.msu').read_bytes() == b'fixed Microsoft MSU bytes'
    assert all((directory / row['filename']).exists() for row in rows)
    with pytest.raises(FileExistsError):
        prereq.stage_prerequisites(directory, 'x64', destination)


def test_pinned_zip_members_must_also_match(offline_inputs):
    directory, rows = offline_inputs
    rows[0]['members'][0]['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='member bytes'):
        prereq.validate_prerequisites(directory, 'x64')


def test_unexpected_zip_members_rejected(offline_inputs):
    directory, rows = offline_inputs
    target = directory / rows[0]['filename']
    with zipfile.ZipFile(str(target), 'a') as stream:
        stream.writestr('../unexpected.exe', b'not approved')
    rows[0].update(bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='member set'):
        prereq.validate_prerequisites(directory, 'x64')


def test_failed_download_leaves_no_partial_payload(tmp_path, monkeypatch):
    directory = tmp_path / 'external'
    row = record('fixed.msu', b'fixed', id='ssu-x64', url='https://download.microsoft.com/fixed.msu')
    monkeypatch.setattr(prereq, 'inputs', lambda architecture: [row])

    class Response(io.BytesIO):
        def geturl(self):
            return row['url']

    monkeypatch.setattr(prereq, 'urlopen', lambda *args, **kwargs: Response(b'corrupted and oversized'))
    with pytest.raises(ValueError, match='exceeds'):
        prereq.download(directory, 'x64')
    assert list(directory.iterdir()) == []


def test_download_rejects_foreign_redirect(tmp_path, monkeypatch):
    row = record('fixed.msu', b'fixed', id='ssu-x64', url='https://download.microsoft.com/fixed.msu')
    monkeypatch.setattr(prereq, 'inputs', lambda architecture: [row])

    class Response(io.BytesIO):
        def geturl(self):
            return 'https://unexpected.example/fixed.msu'

    monkeypatch.setattr(prereq, 'urlopen', lambda *args, **kwargs: Response(b'fixed'))
    with pytest.raises(ValueError, match='redirected'):
        prereq.download(tmp_path / 'external', 'x64')
    assert list((tmp_path / 'external').iterdir()) == []
