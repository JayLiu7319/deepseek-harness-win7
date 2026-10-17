import hashlib
from pathlib import Path
import zipfile

import pytest

from scripts import build_windows_upgrade as builder


@pytest.fixture
def staged_inputs(monkeypatch):
    monkeypatch.setattr(builder,'validate_prerequisites',lambda *_: None)

    def stage(_directory, architecture, destination):
        destination.mkdir()
        result=[]
        for name in ('ssu-'+architecture+'.msu','net472.exe'):
            data=b'shared .NET' if name=='net472.exe' else architecture.encode('ascii')
            (destination/name).write_bytes(data)
            result.append(dict(filename=name,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
        return result

    monkeypatch.setattr(builder,'stage_prerequisites',stage)


def test_upgrade_zip_deduplicates_shared_net_and_prunes_only_verified_staging(tmp_path, staged_inputs):
    output=tmp_path/'output'
    result=builder.build(tmp_path/'external',output)
    assert result['status']=='built' and result['installationExecuted'] is False
    assert result['cleanup']['stagedCopies']==4
    assert not list(output.glob('staged-*'))
    with zipfile.ZipFile(str(output/result['artifact']['path'])) as stream:
        assert stream.namelist().count('prerequisites/net472.exe')==1
        assert stream.read('prerequisites/ssu-x86.msu')==b'x86'
        assert stream.read('prerequisites/ssu-x64.msu')==b'x64'
        assert 'upgrade-win7.bat' in stream.namelist() and 'win7-setup.html' in stream.namelist()
    with pytest.raises(ValueError,match='fresh'):
        builder.build(tmp_path/'external',output)


def test_failed_upgrade_archive_preserves_changed_staged_input(tmp_path, staged_inputs, monkeypatch):
    real_digest=builder.digest
    seen={}
    def changed(path):
        path=Path(path)
        seen[path]=seen.get(path,0)+1
        if path.name=='ssu-x86.msu' and seen[path]==2:
            path.write_bytes(b'changed during archive preparation')
        return real_digest(path)
    monkeypatch.setattr(builder,'digest',changed)
    output=tmp_path/'output'
    with pytest.raises(ValueError,match='changed'):
        builder.build(tmp_path/'external',output)
    assert (output/'staged-x86/ssu-x86.msu').read_bytes()==b'changed during archive preparation'
    assert (output/'offline-upgrade-build.json').is_file()
