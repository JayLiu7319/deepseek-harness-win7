"""Collect real pytest parameters and refuse drift before executing their bodies."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def collect(arguments, output):
    env = dict(os.environ, DSH_RELEASE_COLLECTION_REPORT=str(output))
    env.pop('DSH_RELEASE_PYTEST_OUTPUT', None)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-p', 'scripts.release_pytest_collection',
        '--collect-only', '-q'] + arguments, cwd=str(ROOT), env=env, capture_output=True, timeout=120)
    output.with_suffix('.log').write_bytes(result.stdout + result.stderr)
    return result, json.loads(output.read_text(encoding='utf-8'))


@pytest.mark.parametrize('damage', ['none', 'stale-parameter', 'deselected', 'duplicate'])
def test_actual_collection_guards_parameter_instances_before_test_bodies(tmp_path, damage):
    folder = tmp_path / 'fixture'
    folder.mkdir()
    (folder / 'test_parameters.py').write_text(
        "import pytest\n@pytest.mark.parametrize('backend',['jsonl','jsonl-zstd'])\n"
        "def test_backend(backend):\n    raise AssertionError('collection must not run test bodies')\n", encoding='utf-8')
    expected = ['test_backend[jsonl]', 'test_backend[sqlite]' if damage == 'stale-parameter' else 'test_backend[jsonl-zstd]']
    (folder / 'conftest.py').write_text(
        "def pytest_configure():\n    from scripts import verify_release\n"
        "    verify_release.REQUIRED_REGRESSION = {'test_parameters':set(" + repr(expected) + ")}\n", encoding='utf-8')
    arguments = [str(folder / 'test_parameters.py'), '--confcutdir=' + str(folder), '--rootdir=' + str(folder)]
    if damage == 'deselected':
        arguments += ['-k', 'not zstd']
    elif damage == 'duplicate':
        arguments += [str(folder / 'test_parameters.py')]
    result, report = collect(arguments, tmp_path / 'collection.json')
    assert report['scope'].startswith('Collection identities only')
    if damage == 'none':
        assert result.returncode == 0, result.stdout + result.stderr
        assert report['result'] == 'collection-valid' and report['required_lanes'] == 2
    else:
        assert result.returncode == 4, result.stdout + result.stderr
        assert report['result'] == 'refused'
        assert ('more than once' if damage == 'duplicate' else 'not collected') in report['error']


def test_current_manifest_resolves_actual_collected_parameters(tmp_path):
    result, report = collect(['tests'], tmp_path / 'actual-collection.json')
    assert result.returncode == 0, result.stdout + result.stderr
    assert report['result'] == 'collection-valid'
    assert report['required_lanes'] > 0 and report['collected'] >= report['required_lanes']
