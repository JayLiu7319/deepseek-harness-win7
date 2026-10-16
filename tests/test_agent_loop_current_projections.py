"""rc.3 loop boundaries whose ordering and failure ownership affect consumers."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.cordis.context import Context
from dsh.core.assistant_stream_current import AssistantStreamAttempt
from dsh.core.inbox_current import ReactLoopInbox
from dsh.core.runtime_context_current import RuntimeContextProjection, SystemPromptProjection, CLEARED
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.system_prompt.current import CurrentSystemPrompt, PERSONA_PREFIX_SECTION, PERSONA_SUFFIX_SECTION
from dsh.core.system_prompt import render_prompt
from dsh.session.projections import SessionProjectionsPlugin
from scripts.oracles.agent_loop_current_python import execute
from scripts.oracles.session_format_python import decode


ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'scripts/oracles/agent_loop_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_frozen_actual_source_observations(case):
    assert execute(case,decode)==case['expected']


def message(identity):
    return dict(id=identity,role='user',content=[dict(type='text',text=identity)],source=dict(kind='user'))


async def mount():
    ctx=Context()
    await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(SessionProjectionsPlugin)
    session=ctx.get('sessions').create('inbox')
    return ctx,session


@pytest.mark.asyncio
async def test_claim_observers_see_both_committed_removals_and_captured_batches():
    ctx,session=await mount();seen=[]
    inbox=ReactLoopInbox(ctx.get('sessionProjections'),session,SimpleNamespace(emit=lambda name,payload:seen.append((name,payload,list(inbox.nextTurn),list(inbox.nextStep)))))
    try:
        inbox.append('next-turn',message('turn'));inbox.append('next-step',message('step'))
        captured=inbox.nextStep
        seen.clear()
        claimed=inbox.claim('next-turn',3)
        assert [msg['id'] for msg in claimed]==['step','turn']
        assert [msg['id'] for msg in captured]==['step']
        assert len(seen)==2 and all(turn==[] and step==[] for _,_,turn,step in seen)
        assert all(name=='agent/inbox/claimed' and payload['turn']==3 for name,payload,_,_ in seen)
        assert all('outcome' not in event['data'] for event in session.events[-2:])
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_reentrant_session_observer_reads_projection_before_notification():
    ctx,session=await mount();seen=[]
    inbox=ReactLoopInbox(ctx.get('sessionProjections'),session,SimpleNamespace(emit=lambda *args:seen.append(('inbox',list(inbox.nextTurn)))))
    ctx.on('session/event',lambda subject,event:seen.append(('session',list(inbox.nextTurn))))
    original=message('one')
    try:
        inbox.append('next-turn',original)
        original['content'][0]['text']='changed after call'
        assert [kind for kind,_ in seen]==['session','inbox']
        assert seen[0][1][0]['content'][0]['text']=='one'
        assert seen[1][1][0] is session.events[-1]['data']['inserted'][0]
        with pytest.raises(TypeError):seen[1][1][0]['content'][0]['text']='invalid'
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_rejected_append_has_no_inbox_notification_or_projection_mutation(monkeypatch):
    ctx,session=await mount();seen=[]
    inbox=ReactLoopInbox(ctx.get('sessionProjections'),session,SimpleNamespace(emit=lambda *args:seen.append(args)))
    primary=RuntimeError('writer rejected')
    def reject(*args):raise primary
    monkeypatch.setattr(session,'append',reject)
    try:
        with pytest.raises(RuntimeError) as caught:inbox.append('next-turn',message('one'))
        assert caught.value is primary
        assert not inbox.hasPending and not session.events and not seen
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_empty_and_missing_ids_still_participate_in_global_uniqueness():
    ctx,session=await mount()
    inbox=ReactLoopInbox(ctx.get('sessionProjections'),session,SimpleNamespace(emit=lambda *args:None))
    try:
        for identity in ('',None):
            original=message(identity)
            if identity is None:original.pop('id')
            inbox.clear();inbox.append('next-step',original)
            with pytest.raises(ValueError,match='already pending'):inbox.append('next-turn',original)
            assert len(session.events[-1]['data']['inserted'])==1
    finally:await ctx.fiber.dispose()


def test_stream_settlement_orders_durability_before_end_and_preserves_failure_identity():
    order=[];revision=[0]
    def next_revision():revision[0]+=1;return revision[0]
    live=AssistantStreamAttempt('session',2,next_revision,3,4,lambda frame:order.append(frame))
    live.start();chunk=dict(type='text-delta',index=0,text='safe');live.push(chunk);chunk['text']='unsafe'
    before=live.stream;live.push(dict(type='text-delta',index=0,text=' suffix'))
    def append():order.append('durable');return 6
    live.settle('assistant/message',append)
    assert order[-2]=='durable' and order[-1]['outcome']['seq']==6
    assert before[0]['texts']==['safe'] and live.stream[0]['texts']==['safe',' suffix']
    assert live.blocks()==[dict(type='text',text='safe suffix')]
    primary=RuntimeError('same failure')
    def reject():raise primary
    with pytest.raises(RuntimeError) as caught:live.settle('assistant/attempt',reject)
    assert caught.value is primary and live.ended and order[-1]['outcome']==dict(kind='abandoned')


@pytest.mark.asyncio
async def test_runtime_ignores_subjectless_and_foreign_session_events():
    ctx,session=await mount();projection=RuntimeContextProjection(ctx,session)
    owned=message('context');owned['source']=dict(kind='plugin',plugin='@deepseek-ai/dsh-system-prompt')
    event=dict(type='user/message',seq=0,data=owned)
    try:
        ctx.emit('session/event',None,event)
        other=ctx.get('sessions').create('other');other.append('user/message',owned,'append')
        assert projection.project('',[]) is None
        session.append('user/message',owned,'append')
        assert projection.project('',[])['content'][0]['text']==CLEARED
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_current_persona_prefix_suffix_order_and_complete_override():
    ctx=Context()
    try:
        await ctx.plugin(CurrentSystemPrompt,dict(personaPrefix='prefix',personaSuffix='suffix'))
        prompt=ctx.get('systemPrompt')
        prompt.section(dict(name='tool',order=1000,text='tool'))
        prompt.section(dict(name='web',order=prompt.getSectionOrder('WEB_SURFACE'),text='web'))
        assert render_prompt(await prompt.assemble())=='You are an AI agent powered by DeepSeek Harness.\n\nprefix\n\ntool\n\nweb\n\nsuffix'
        remove=prompt.section(dict(name='complete',order=500,text='complete',complete=True))
        assert render_prompt(await prompt.assemble())=='complete'
        remove()
        assert [part['name'] for part in (await prompt.assemble())['sections']]==['harness:identity',PERSONA_PREFIX_SECTION,'tool','web',PERSONA_SUFFIX_SECTION]
    finally:await ctx.fiber.dispose()
