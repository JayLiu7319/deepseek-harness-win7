"""Actual rc.3 goal parity, durable failure and mutation detachment."""
import json
from pathlib import Path

import pytest

from dsh.goal.fold_current import DEFINITION
from scripts.oracles.agent_loop_current_python import execute as units
from scripts.oracles.agent_machine_current_python import execute as machine
from scripts.oracles.session_format_python import decode

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT/'scripts/oracles/goal_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_goal_contract(case):
    execute = machine if case['kind']=='machine-current' else units
    assert execute(case, decode) == case['expected']


def test_checkpoint_parse_detaches_host_state_and_strips_only_nested_unknowns():
    current = dict(goal=dict(id='g', revision=1, objective='finish', phase='active', maxGoalRounds=2,
                            extra=True, blockedReason=dict(code='', message='', extra=True)),
                   roundsStarted=0, createdAt=0, updatedAt=0, extra=True)
    state = dict(current=current, seenGoalIds=['g'], failure=None)
    parsed = DEFINITION['stateSchema'](state)
    assert 'extra' not in parsed['current'] and 'extra' not in parsed['current']['goal']
    assert parsed['current']['goal']['blockedReason']==dict(code='', message='')
    parsed['current']['goal']['objective']='changed'
    parsed['seenGoalIds'].append('other')
    assert current['goal']['objective']=='finish' and state['seenGoalIds']==['g']


def test_failed_projection_retains_last_valid_view_and_stops_future_owned_replay():
    state=DEFINITION['init']()
    state=DEFINITION['apply'](state,dict(type='goal/change',seq=0,data=dict(kind='goal/change',version=2)))
    assert state['failure']=='goal replay failed at session event 0: unsupported goal change version 2'
    assert DEFINITION['apply'](state,dict(type='goal/change',seq=1,data=None)) is state
    assert DEFINITION['wire']['view'](state) is None
