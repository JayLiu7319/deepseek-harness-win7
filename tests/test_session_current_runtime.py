"""Real Source Session prefixes plus aliasing, publication and incremental boundaries."""
import copy
import json
from pathlib import Path

import pytest

from dsh.core.session.current_session import CurrentSession,CurrentSessionStore
from dsh.core.session.current_surface import CurrentSurfaceManager
from dsh.core.session.current import adoptSessionEvent
from dsh.core.session.json import FrozenDict
from dsh.cordis.errors import ThrownValueError
from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/session_runtime_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=[case['case'] for case in CASES])
def test_actual_detached_session_call_prefix(case):
    expected=dict(case=case['case'],outcome='value',value=case['expected'])
    assert json_equal(json.loads(json.dumps(observe(case))),expected)


def user(seq=0,text='user'):
    return dict(type='user/message',seq=seq,time=1,surfaceOp='append',data=dict(id='user-%s'%seq,
        role='user',content=[dict(type='text',text=text)],source=dict(kind='user')))


def header(seeded=False):
    return dict(version=3,id='current',createdAt=1,isSeeded=seeded,delegationDepth=0)


def test_snapshot_detaches_but_restore_adopts_without_freezing_events():
    seed=[user()]
    snapshot=CurrentSession.create('snapshot',seed)
    restored=CurrentSession.from_restore('current',seed,header(),0,'detached')
    assert restored.eventAt(0) is seed[0]
    assert not isinstance(seed[0],FrozenDict)
    seed[0]['data']['content'][0]['text']='changed owned event'
    assert restored.eventAt(0)['data']['content'][0]['text']=='changed owned event'
    assert snapshot.deriveMessages()[0]['content'][0]['text']=='user'
    with pytest.raises(TypeError):snapshot.eventAt(0)['data']['content'][0]['text']='bad'


def test_adoption_freezes_only_identified_message_and_preserves_event_identity():
    event=dict(type='system/message',seq=0,time=1,surfaceOp='append',data=dict(
        message=dict(id='system',role='system',source=dict(kind='plugin',plugin='test'),content=[]),extension=dict(value=1)))
    assert adoptSessionEvent(event) is event
    with pytest.raises(TypeError):event['data']['message']['content'].append(dict(type='text',text='bad'))
    event['data']['extension']['value']=2
    assert event['data']['extension']['value']==2


def test_seeded_snapshot_always_appends_own_inherited_marker_even_after_ancestor_marker():
    seed=[dict(type='session/end-seed',seq=0,time=1,data=dict(inherited=True))]
    session=CurrentSession.create('current',seed,header(True),1)
    assert session.inheritedEventCount==1
    assert session.firstLiveSeq==1
    assert session.ownEvents()[0]['data']==dict(inherited=True)
    assert session.ownEvents()[0]['seq']==1
    with pytest.raises(ValueError,match='constructor seed must equal'):
        CurrentSession.create('current',seed,header(True),0)


@pytest.mark.parametrize('error,detail',[(ValueError('validator failed'),'validator failed'),
    (ThrownValueError('validator failed'),'invalid surface metadata')])
def test_seed_validation_wraps_native_error_and_non_error_carrier(monkeypatch,error,detail):
    def fail(*args):raise error
    monkeypatch.setattr(CurrentSurfaceManager,'validate_next',fail)
    with pytest.raises(ValueError,match='invalid seed event at index 0: '+detail):
        CurrentSession.create('current',[user()])


def test_floating_json_sequence_projects_and_negative_zero_provenance_refuses():
    event=user(0.0)
    restored=CurrentSession.from_restore('current',[event],header(),0,'detached')
    assert restored.deriveMessages()==[event['data']]
    event=user(2)
    event['sourceEventSeqs']=[-0.0]
    with pytest.raises(ValueError,match='non-negative safe integers'):adoptSessionEvent(event)


def test_incremental_surface_plans_before_commit_and_reuses_exact_candidate():
    log=[]
    manager=CurrentSurfaceManager(log)
    first=user()
    manager.validateNext(first)
    assert manager.nodes==[]
    log.append(first)
    assert manager.nodes==[0]
    bad=user(1)
    bad['surfaceOp']=dict(op='replace',startSeq=0,endSeq=0)
    with pytest.raises(ValueError,match='must include every shadowed'):manager.validateNext(bad)
    assert manager.nodes==[0]
    good=copy.deepcopy(bad);good['sourceEventSeqs']=[0]
    manager.validateNext(good)
    assert manager.replaceGeneration==0
    log.append(good)
    assert manager.nodes==[1]
    assert manager.replaceGeneration==1


def test_current_store_prepares_owned_state_without_publishing_and_forks_tagged_cut():
    store=CurrentSessionStore()
    event=user()
    session=store.prepare('current',dict(seed=[event],meta=header(),inheritedEventCount=0,eventState='detached'))
    assert session.eventAt(0) is event
    assert store.get('current') is None
    store.enter(session)
    child=store.fork(session,0.0,'child')
    assert child.header.version==3
    assert child.inheritedEventCount==1
    assert child.ownEvents()[0]['data']==dict(inherited=True)


def test_native_conveniences_keep_canonical_system_head_and_embedded_stream():
    session=CurrentSession.create('current')
    session.append_event('system/message',dict(message=dict(id='head',role='system',content=[],source=dict(kind='plugin',plugin='test'))))
    event=session.append_assistant_message('reply')
    assert event['data']['stream']==[]
    assert session.deriveMessages()[0]['content'][0]['text']=='reply'
    child=session.fork('child')
    assert child.header.version==3
    assert child.header.isSeeded is True
