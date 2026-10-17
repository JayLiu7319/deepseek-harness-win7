"""Retained capability observer must exercise the current provider closure."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import rc1_capabilities_oracle as oracle


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def paired(tmp_path_factory):
    output = tmp_path_factory.mktemp('current-capabilities') / 'pair'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/rc1_capabilities_oracle.py'),
        '--output', str(output)], capture_output=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    source = json.loads((output / 'source.json').read_text(encoding='utf-8'))
    native = json.loads((output / 'native.json').read_text(encoding='utf-8'))
    assert set(source['observations']) == oracle.REQUIRED
    oracle.validate_runtime(native, ROOT, oracle.digest(source['observations']), native['inputSha256'])
    return source, native


def test_actual_current_capabilities_keep_all_original_categories(paired):
    source, native = paired
    assert source['observations'] == native['observations']
    assert len(native['observations']['chunkDecode']) == 9
    assert [len(row[0]['texts']) for row in native['observations']['chunkPack']] == [2, 3, 1025, 3]
    assert native['observations']['projectionLineage']['initial']['val']['cut'] == 2


@pytest.mark.parametrize('module', sorted(oracle.CURRENT_MODULES))
def test_capability_observer_rejects_missing_current_provider(paired, module):
    source, original = paired
    native = copy.deepcopy(original)
    del native['modules'][module]
    with pytest.raises(ValueError):
        oracle.validate_runtime(native, ROOT, oracle.digest(source['observations']), native['inputSha256'])


@pytest.mark.parametrize('category', sorted(oracle.REQUIRED))
def test_capability_observer_rejects_missing_current_category(paired, category):
    source, original = paired
    native = copy.deepcopy(original)
    del native['observations'][category]
    native['sourceObservationsSha256'] = oracle.digest(native['observations'])
    with pytest.raises(ValueError):
        oracle.validate_runtime(native, ROOT, oracle.digest(source['observations']), native['inputSha256'])
