"""Current Agent machine, identity scope, ownership and cancellation regressions."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.cordis.context import Context
from dsh.core.agent_current import CurrentAgentPlugin
from dsh.core.agent_loop_current import CurrentAgentLoopPlugin
from dsh.core.agent_dispatch_current import agent_events, assemble_context_for
from dsh.core.agent import AgentOptions
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.scope import scope_of
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.core.tools import ToolsPlugin
from dsh.llm.agent_request import is_agent_loop_request
from dsh.llm.llm_service import LlmError
from dsh.llm.runtime_current import CurrentLlmRuntime
from dsh.session.projections import SessionProjectionsPlugin
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin
from scripts.oracles.agent_machine_current_python import execute, ScriptAdapter
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.generate_agent_loop_current_cases import message
from scripts.oracles.session_format_python import decode


ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'scripts/oracles/agent_machine_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_machine_observation(case):
    assert execute(case,decode)==case['expected']


async def mount(tmp_path=None):
    ctx=Context()
    for plugin in (CurrentLlmRuntime,CurrentSessionPlugin,SessionProjectionsPlugin,CurrentSystemPrompt,ToolsPlugin,CurrentAgentPlugin):
        await ctx.plugin(plugin)
    if tmp_path is not None:await ctx.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=str(tmp_path/'sessions'),compression='none'))
    await ctx.plugin(CurrentAgentLoopPlugin,dict(agents=[]))
    ctx.get('llm').registerAdapter(['script'],ScriptAdapter(dict(script=[response() for _ in range(12)])))
    return ctx


async def create(ctx,sid,**kwargs):
    return await ctx.get('agents').create(dict(sessionId=sid,options=dict(provider='script',model='model'),**kwargs))


@pytest.mark.asyncio
async def test_agent_identity_scopes_route_notifications_and_prompt_providers():
    ctx=await mount();seen=[];requests=[];handles=[]
    def setup(scope,agent):
        assert scope_of(scope) is agent
        scope.on('agent/status',lambda payload:seen.append((agent.id,payload['agent'].id,payload['status'])))
        scope.get('systemPrompt').section(dict(name='own',order=5,text=agent.id))
    ctx.on('llm/stream',lambda request,next:(requests.append(request),next())[1])
    try:
        for sid in ('left','right'):handles.append(await create(ctx,sid,setup=setup))
        for handle in handles:handle.agent.followup(message('input-'+handle.agent.id))
        await asyncio.gather(*(handle.agent.whenIdle() for handle in handles))
        assert all(receiver==subject for receiver,subject,_ in seen) and len(seen)==4
        for request in requests:
            system=[msg for msg in request['messages'] if msg['role']=='system']
            assert request['sessionId'] in system[0]['content'][0]['text']
            assert ('right' if request['sessionId']=='left' else 'left') not in system[0]['content'][0]['text']
        assert assemble_context_for(handles[0].agent)['scope'] is handles[0].agent
    finally:
        for handle in handles:await handle.dispose()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_explicit_parent_is_independent_of_accessing_agent_scope():
    ctx=await mount();handles=[]
    try:
        parent=await create(ctx,'parent');handles.append(parent)
        implicit=await create(parent.agent.ctx,'implicit');handles.append(implicit)
        explicit=await create(ctx,'explicit',parentAgent=parent.agent);handles.append(explicit)
        registry=ctx.get('agents')
        assert not registry.isOwnedBy('implicit',parent.agent)
        assert registry.isOwnedBy('explicit',parent.agent)
        assert {agent.id for agent in registry.roots()}=={'parent','implicit'}
        assert explicit.agent.session.header.parentSession is None
    finally:
        for handle in reversed(handles):await handle.dispose()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_sync_created_failure_vetoes_and_releases_writer_async_rejection_does_not(tmp_path):
    ctx=await mount(tmp_path);primary=RuntimeError('veto');rejected=asyncio.Event();later=[]
    def fail(payload):raise primary
    withdraw=ctx.on('agent/created',fail)
    try:
        with pytest.raises(RuntimeError) as caught:await create(ctx,'fresh')
        assert caught.value is primary
        assert not ctx.get('agents').list() and not ctx.get('sessions').list()
        assert not ctx.get('sessionPersistence').tracker.writers
        assert await ctx.get('sessionPersistence').stat('fresh') is None
        withdraw()
        async def async_fail(payload):rejected.set();raise RuntimeError('returned promise')
        ctx.on('agent/created',async_fail);ctx.on('agent/created',lambda payload:later.append(payload['agent'].id))
        handle=await create(ctx,'fresh')
        await asyncio.wait_for(rejected.wait(),1)
        assert later==['fresh']
        await handle.dispose()
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_non_veto_dispatch_fuses_subject_and_runs_async_prefix_before_later_observer():
    ctx=await mount();handle=await create(ctx,'dispatch');agent=handle.agent;seen=[];settled=asyncio.Event();barrier=asyncio.Event()
    def fail(payload):seen.append('sync');raise RuntimeError('contained')
    async def reject(payload):
        seen.append('prefix');await barrier.wait();seen.append('tail');settled.set();raise RuntimeError('contained async')
    ctx.on('agent/status',fail);ctx.on('agent/status',reject)
    ctx.on('agent/status',lambda payload:seen.append(payload['agent']))
    try:
        agent_events(ctx,agent).emit('agent/status',dict(agent=object(),status='test'))
        assert seen==['sync','prefix',agent]
        barrier.set();await asyncio.wait_for(settled.wait(),1)
        assert seen[-1]=='tail'
    finally:await handle.dispose();await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_maintenance_reserves_immediately_latches_wake_and_when_idle_joins():
    ctx=await mount();handle=await create(ctx,'maintenance');agent=handle.agent;entered=asyncio.Event();release=asyncio.Event();signals=[]
    async def job(signal):signals.append(signal);entered.set();await release.wait();return 'done'
    try:
        task=agent.runMaintenance(job)
        assert entered.is_set() and agent.status=='idle'
        with pytest.raises(RuntimeError,match='already has active work'):agent.runMaintenance(job)
        idle=asyncio.create_task(agent.whenIdle())
        agent.followup(message('wake'))
        assert not any(event['type']=='turn/start' for event in agent.session.events)
        await asyncio.sleep(0);assert not idle.done()
        release.set();assert await task=='done';await asyncio.wait_for(idle,2)
        assert agent.status=='idle' and len([event for event in agent.session.events if event['type']=='assistant/message'])==1
        assert not signals[0].aborted
    finally:release.set();await handle.dispose();await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_disposal_cancels_active_stream_drains_closing_events_before_detach(tmp_path):
    ctx=await mount(tmp_path);entered=asyncio.Event();closed=asyncio.Event();observations=[]
    async def stream(request):
        try:
            yield dict(type='text-delta',index=0,text='partial')
            entered.set();await request['signal'].wait_aborted();request['signal'].throwIfAborted()
        finally:closed.set()
    ctx.get('llm').registerAdapter(['hanging'],SimpleNamespace(stream=stream))
    handle=await ctx.get('agents').create(dict(sessionId='active',options=dict(provider='hanging',model='model')))
    ctx.on('agent/disposed',lambda payload:observations.append((closed.is_set(),not ctx.get('sessionPersistence').tracker.writers)))
    try:
        handle.agent.followup(message('wake'));await asyncio.wait_for(entered.wait(),2)
        await asyncio.wait_for(handle.dispose(),2)
        assert observations==[(True,True)]
        read=await ctx.get('sessionPersistence').open('active','read')
        try:events=(await read.read())['events']
        finally:await read.close()
        assert events[-1]['type']=='turn/end' and events[-1]['data']['reason']==dict(kind='aborted',reason=dict(kind='disposed'))
        assert events[-3]['type']=='assistant/message' and events[-3]['data']['interrupted'] is True
    finally:await ctx.fiber.dispose()


@pytest.mark.parametrize('service', ['agents', 'sessions', 'llm', 'tools', 'systemPrompt', 'sessionProjections'])
@pytest.mark.parametrize('active', [False, True], ids=['idle', 'streaming'])
@pytest.mark.asyncio
async def test_dependency_loss_drains_machine_before_identity_scope_disposal(service, active):
    ctx = Context()
    providers = dict(agents=CurrentAgentPlugin, sessions=CurrentSessionPlugin,
                     llm=CurrentLlmRuntime, tools=ToolsPlugin,
                     systemPrompt=CurrentSystemPrompt, sessionProjections=SessionProjectionsPlugin)
    fibers = {name: await ctx.plugin(plugin) for name, plugin in providers.items()}
    loop = await ctx.plugin(CurrentAgentLoopPlugin, dict(agents=[]))
    entered, closed = asyncio.Event(), asyncio.Event()

    async def stream(request):
        try:
            yield dict(type='block-start', index=0, blockType='text')
            yield dict(type='text-delta', index=0, text='partial')
            entered.set()
            await request['signal'].wait_aborted()
            request['signal'].throwIfAborted()
        finally:
            closed.set()

    registry, sessions = ctx.get('agents'), ctx.get('sessions')
    factory = ctx.get('agentLoop')
    ctx.get('llm').registerAdapter(['hanging'], SimpleNamespace(stream=stream))
    handle = await registry.create(dict(sessionId='dependency-loss', options=dict(provider='hanging', model='model')))
    try:
        if active:
            handle.agent.followup(message('wake'))
            await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(fibers[service].dispose(), 2)
        assert ctx.get('agentLoop') is None
        assert registry.get('dependency-loss') is None
        assert sessions.get('dependency-loss') is None
        if active:
            assert closed.is_set()
            assert handle.agent.session.events[-1]['type'] == 'turn/end'
        # The caller can release its handle again after the owner has retired.
        await asyncio.wait_for(handle.dispose(), 2)
        with pytest.raises(RuntimeError, match='inactive context'):
            await factory.create_agent('retired')
        await ctx.plugin(providers[service])
        assert ctx.get('agentLoop') is not factory
        replacement = await ctx.get('agents').create(session_id='replacement')
        await replacement.dispose()
    finally:
        await handle.dispose()
        await loop.dispose()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_request_is_frozen_marked_and_replayable_with_exact_signal_identity():
    ctx=await mount();handle=await create(ctx,'request');requests=[];initiators=[]
    def capture(request,next):
        assert request['signal'] is handle.agent.phase['abort'].signal
        requests.append(request);initiators.append(ctx.get('agents').requireInitiator());return next()
    ctx.on('llm/stream',capture)
    try:
        handle.agent.followup(message('wake'));await handle.agent.whenIdle()
        request=requests[0]
        assert is_agent_loop_request(request) and initiators==[handle.agent]
        with pytest.raises(TypeError):request['messages'].append(message('invalid'))
        with pytest.raises(TypeError):request['messages'][0]['content'][0]['text']='invalid'
        assert request['messages']==handle.agent.session.deriveMessages()[:-1]
        assert 'system' not in request
    finally:await handle.dispose();await ctx.fiber.dispose()


@pytest.mark.parametrize('value',[None,'replace-head',False,1,{}])
@pytest.mark.asyncio
async def test_invalid_system_prompt_capability_rejected_before_input_admission(value):
    ctx=await mount();ctx.get('llm').registerAdapter(['invalid'],ScriptAdapter(dict(systemPromptUpdate=value,script=[response()])))
    handle=await ctx.get('agents').create(dict(sessionId='invalid',options=dict(provider='invalid',model='model')))
    try:
        handle.agent.followup(message('wake'));await handle.agent.whenIdle()
        events=handle.agent.session.events
        assert not any(event['type'] in ('system/message','user/message','request/header') for event in events)
        assert events[-1]['data']['reason']['error']['code']=='INVALID_MODEL_INFO'
    finally:await handle.dispose();await ctx.fiber.dispose()
