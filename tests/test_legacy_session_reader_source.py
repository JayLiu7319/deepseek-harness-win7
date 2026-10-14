"""The retired alpha provider is historical input, not an rc.1 provider."""
import copy
import json
import subprocess
import sys

import pytest

from scripts import legacy_session_reader_oracle as oracle


@pytest.fixture(scope='module')
def qualified(tmp_path_factory):
    output = tmp_path_factory.mktemp('legacy-reader') / 'reader.json'
    result = subprocess.run([sys.executable, str(oracle.ROOT / 'scripts/legacy_session_reader_oracle.py'),
                             '--output', str(output)], capture_output=True, timeout=90)
    assert result.returncode == 0, (result.stdout + result.stderr).decode('utf-8', errors='replace')
    return json.loads(output.read_text(encoding='utf-8'))


def test_actual_archived_source_database_reads_exports_and_continues(qualified):
    oracle.validate_runtime(qualified, oracle.ROOT)
    assert len(qualified['rows']) == 4


@pytest.mark.parametrize('damage', ['root', 'runtime', 'module', 'asset', 'fixture', 'history', 'missing', 'outcome'])
def test_compatibility_receipt_rejects_another_candidate_or_incomplete_observation(qualified, damage):
    report = copy.deepcopy(qualified)
    if damage == 'root':
        report['root'] += '-foreign'
    elif damage == 'runtime':
        report['python'] = [3, 9, 0]
    elif damage in ('module', 'asset'):
        key = 'dsh/session/sqlite_legacy_reader.py' if damage == 'module' else 'dsh/session/bin/sqlite3.dll'
        report['modules'][key] = '0' * 64
    elif damage == 'fixture':
        report['fixtureSha256'] = '0' * 64
    elif damage == 'history':
        report['historicalSource'] = 'a66e4702047846cdaa10c66c9d3df3951f5ea70d'
    elif damage == 'missing':
        report['rows'].pop()
    else:
        report['rows'][0]['readonly'] = False
    with pytest.raises(ValueError):
        oracle.validate_runtime(report, oracle.ROOT)
