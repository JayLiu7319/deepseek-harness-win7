import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

from scripts import package_release_diagnostics as diagnostics


def test_diagnostics_keeps_failures_hidden_files_and_empty_directories(tmp_path):
    source = tmp_path / 'observations'
    source.mkdir()
    (source / '.hidden').write_bytes(b'raw failed observation')
    (source / 'empty').mkdir()
    (source / 'pytest.xml').write_text('<testsuites><testsuite><testcase name="broken"><failure>original stack</failure></testcase><testcase name="skip"><skipped/></testcase></testsuite></testsuites>', encoding='utf-8')
    stream = io.StringIO()
    diagnostics.print_summary(source, stream)
    assert 'original stack' in stream.getvalue() and 'REGRESSION failure: ::broken' in stream.getvalue()
    assert json.loads(stream.getvalue().splitlines()[0]) == dict(collected=2, failed_or_error=1, skipped=1)
    destination = tmp_path / 'diagnostics.zip'
    diagnostics.package(source, destination)
    with zipfile.ZipFile(str(destination)) as archive:
        assert archive.testzip() is None
        assert archive.read('.hidden') == b'raw failed observation'
        assert 'empty/' in archive.namelist()
        assert 'original stack' in archive.read('pytest.xml').decode('utf-8')
        inventory = json.loads(archive.read(diagnostics.MANIFEST))
        assert all(row.get('sha256') for row in inventory['members'] if row['kind'] == 'file')
    assert (source / '.hidden').read_bytes() == b'raw failed observation'


def test_diagnostics_never_follows_external_or_cyclic_directory_link(tmp_path):
    source = tmp_path / 'observations'
    source.mkdir()
    foreign = tmp_path / 'foreign'
    foreign.mkdir()
    (foreign / 'must-not-upload').write_bytes(b'foreign bytes')
    for name, target in [('foreign-link', foreign), ('cycle', source)]:
        link = source / name
        if os.name == 'nt':
            subprocess.check_call(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)])
        else:
            link.symlink_to(target, target_is_directory=True)
    destination = tmp_path / 'diagnostics.zip'
    try:
        inventory = diagnostics.package(source, destination)
        assert len(inventory['members']) == 2
        assert all(row['kind'] == 'opaque-link' for row in inventory['members'])
        assert all(row.get('reparseHex') if os.name == 'nt' else row.get('target') for row in inventory['members'])
        with zipfile.ZipFile(str(destination)) as archive:
            assert archive.namelist() == [diagnostics.MANIFEST]
        assert (foreign / 'must-not-upload').read_bytes() == b'foreign bytes'
        with pytest.raises(ValueError, match='Linked diagnostics root'):
            diagnostics.print_summary(source / 'foreign-link', io.StringIO())
        with pytest.raises(ValueError, match='Linked diagnostics root'):
            diagnostics.package(source / 'foreign-link', tmp_path / 'foreign.zip')
    finally:
        for name in ('foreign-link', 'cycle'):
            link = source / name
            if os.name == 'nt':
                os.rmdir(str(link))
            else:
                link.unlink()


@pytest.mark.parametrize('damage', ['inside', 'existing', 'reserved'])
def test_diagnostics_refuses_unowned_archive_and_inventory_replacement(tmp_path, damage):
    source = tmp_path / 'observations'
    source.mkdir()
    destination = tmp_path / 'diagnostics.zip'
    error = ValueError
    if damage == 'inside':
        destination = source / 'diagnostics.zip'
    elif damage == 'existing':
        destination.write_bytes(b'prior unresolved carrier')
        error = FileExistsError
    else:
        (source / diagnostics.MANIFEST).write_bytes(b'prior observation')
    with pytest.raises(error):
        diagnostics.package(source, destination)
    if damage == 'existing':
        assert destination.read_bytes() == b'prior unresolved carrier'
    if damage == 'reserved':
        assert (source / diagnostics.MANIFEST).read_bytes() == b'prior observation'


def test_actual_diagnostics_cli_preserves_failed_summary_and_xml(tmp_path):
    source = tmp_path / 'observations'
    source.mkdir()
    (source / 'summary.json').write_text('{"result":"failed","publishable":false}', encoding='utf-8')
    (source / 'pytest.xml').write_text('<testsuites><testsuite><testcase name="setup"><error>raw setup error</error></testcase></testsuite></testsuites>', encoding='utf-8')
    destination = tmp_path / 'diagnostics.zip'
    result = subprocess.run([sys.executable, '-B', diagnostics.__file__, '--source', str(source), '--archive', str(destination)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'raw setup error' in result.stdout and '"publishable":false' in result.stdout
    with zipfile.ZipFile(str(destination)) as archive:
        assert archive.testzip() is None
        assert json.loads(archive.read('summary.json')) == dict(result='failed', publishable=False)


@pytest.mark.parametrize('xml', [None, b'<testsuites><testcase'])
def test_missing_or_truncated_xml_preserves_raw_carrier_without_invented_counts(tmp_path, xml):
    source = tmp_path / 'observations'
    source.mkdir()
    if xml is not None:
        (source / 'pytest.xml').write_bytes(xml)
    stream = io.StringIO()
    diagnostics.print_summary(source, stream)
    assert 'no final test counts inferred' in stream.getvalue()
    destination = tmp_path / 'diagnostics.zip'
    diagnostics.package(source, destination)
    with zipfile.ZipFile(str(destination)) as archive:
        assert archive.testzip() is None
        if xml is not None:
            assert archive.read('pytest.xml') == xml
