"""Real Source v2 migrations, standalone streaming stages and writer admission."""
import json
from pathlib import Path

import pytest

from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_v2_logical_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=[case['case'] for case in CASES])
def test_released_v2_logical_observation(case):
    assert json_equal(json.loads(json.dumps(observe(case))), dict(case['expected'], case=case['case']))
