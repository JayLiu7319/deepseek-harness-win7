"""Current installed admission and the actual build-static historical chain."""
import json
from pathlib import Path

import pytest

from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

ROOT = Path(__file__).resolve().parents[1]
CASES = []
for name in ('session_catalog_cases', 'session_current_cases'):
    CASES.extend(json.loads((ROOT/'scripts/oracles'/('%s.json' % name)).read_text(encoding='utf-8')))


@pytest.mark.parametrize('case', CASES, ids=[case['case'] for case in CASES])
def test_actual_catalog_and_installed_admission(case):
    assert json_equal(json.loads(json.dumps(observe(case))), dict(case['expected'], case=case['case']))
