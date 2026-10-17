"""Frozen observations of the unchanged current transport-free proxy policy."""
import json
from pathlib import Path

import pytest

from scripts.oracles.http_proxy_current_python import execute
from scripts.session_format_oracle import json_equal


CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/http_proxy_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_current_proxy_policy(case):
    assert json_equal(execute(case), case['expected'])
