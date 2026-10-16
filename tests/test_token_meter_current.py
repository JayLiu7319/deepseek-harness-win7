"""Complete current measurements, durable projection checkpoints and atomic replay."""
import json
from pathlib import Path

import pytest

from scripts.oracles.agent_loop_current_python import execute as units
from scripts.oracles.agent_machine_current_python import execute as machine
from scripts.oracles.session_format_python import decode
from dsh.llm.token_meter_current import CurrentTokenMeter
from dsh.llm.token_projections_current import CONTEXT_BREAKDOWN


ROOT=Path(__file__).resolve().parents[1]
JOURNEYS=json.loads((ROOT/'scripts/oracles/token_meter_current_cases.json').read_text(encoding='utf-8'))
UNITS=json.loads((ROOT/'scripts/oracles/token_meter_units_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',JOURNEYS,ids=lambda case:case['case'])
def test_actual_source_measurement_and_projections(case):assert machine(case,decode)==case['expected']


@pytest.mark.parametrize('case',UNITS,ids=lambda case:case['case'])
def test_actual_source_pricing_and_checkpoint_admission(case):assert units(case,decode)==case['expected']


def test_fallible_replay_keeps_same_unread_event_and_previous_surface():
    class Restored:
        events=[dict(type='system/message',seq=0,data=dict(message=dict(role='system',content=[])),surfaceOp='append'),
                dict(type='system/message',seq=1,data=dict(message=dict(role='system',content=[])),surfaceOp=dict(op='replace',startSeq=8,endSeq=8))]
    session=Restored();meter=CurrentTokenMeter()
    for repeat in range(2):
        with pytest.raises(ValueError,match='invalid current range 8-8'):meter.measure(session)
        state=meter._states[session]
        assert state['consumedEvents']==1 and [node['seq'] for node in state['surface']]==[0]


def test_breakdown_checkpoint_detaches_and_retains_last_nonempty_system():
    definition=CONTEXT_BREAKDOWN
    state=definition['init']({},0)
    for seq,text in enumerate(('head','tail','')):
        state=definition['apply'](state,dict(type='system/message',seq=seq,surfaceOp='append',data=dict(message=dict(role='system',content=[dict(type='text',text=text)] if text else []))))
    before=state['breakdown']
    assert before==dict(systemTokens=5,toolsTokens=0,messageTokens=5)
    restored=definition['stateSchema'](state)
    restored['nodes'][0]['heuristicTokens']=100
    assert state['nodes'][0]['heuristicTokens']==5
