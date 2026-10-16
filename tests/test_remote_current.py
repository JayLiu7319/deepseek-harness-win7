"""Current Remote protocol against actual mounted Agent and Gateway services."""
import json
from pathlib import Path

import pytest

from scripts.oracles.agent_machine_current_python import execute
from scripts.oracles.session_format_python import decode

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/remote_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_current_remote_contract(case):
    result = execute(case, decode)
    assert result == case['expected']
    rows = result['results']
    assert rows[0] == dict(outcome='value', value=None)
    if case['case'] == 'remote-current-agent-context':
        assert rows[1]['value'] == dict(exact=True, identityPresent=False, reversePresent=False)
    if 'waterfall-' in case['case'] or 'rejection-' in case['case']:
        frame = rows[3]['value']
        assert frame['type'] == 'waterfall' and frame['agentId'] == 'machine'
        assert 'agent' not in frame['request'] and 'signal' not in frame['request']
    if case['case'] == 'remote-current-goal':
        assert rows[2]['outcome'] == 'value' and rows[3]['value']['objective'] == 'finish'
    if case['case'] == 'remote-current-cancel':
        assert rows[5]['value']['type'] == 'cancel'
        assert rows[6]['error']['cause'] == 'cancelled by owner'
