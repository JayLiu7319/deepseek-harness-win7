"""Complete rc.3 Session assembly over real Agent, persistence, upload and history."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.api.session_current import CurrentSessionController
from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.core.abort import AbortController
from dsh.core.model_selection import AgentDefaultModelConfig
from dsh.host.connection.current import CurrentHostConnection
from dsh.host.file_upload_current import CurrentFileUploads
from dsh.interaction.commands_current import CurrentCommandRuntime
from dsh.session.canonical_title import SessionTitleService
from dsh.session.query_current import CurrentSessionQueryService
from dsh.typert.current import CurrentTypertRegistry
from dsh.typert.remote import RemoteError
from scripts.oracles.session_facade_current_python import execute
from scripts.session_format_oracle import json_equal
from tests.test_agent_machine_current import mount
from tests.test_file_upload_current import unlock_owned

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/session_facade_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_session_facade(case):
    assert json_equal(execute(case),case['expected'])


async def mounted(tmp_path):
    ctx=await mount(tmp_path)
    await ctx.plugin(CurrentTypertRegistry)
    await ctx.plugin(AgentDefaultModelConfig,dict(provider='script',model='model'))
    await ctx.plugin(CurrentCommandRuntime)
    await ctx.plugin(CurrentLocalAttachmentStore,dict(dshHome=str(tmp_path)))
    CurrentHostConnection(ctx,[],SimpleNamespace(is_authenticated=lambda _:True))
    await ctx.plugin(CurrentFileUploads)
    await ctx.plugin(SessionTitleService,dict(fallbackMaxWords=5,fallbackMaxBytes=40,maxTitleBytes=80))
    ctx.set_service('workspaceRegistry',SimpleNamespace(list=lambda:[]))
    ctx.set_service('sessionQuery',CurrentSessionQueryService(ctx))
    ctx.get('sessionProjections').register(dict(key='agentPreset',stateVersion=1,stateSchema=lambda value:value,init=lambda header,_:header.agentPreset,apply=lambda state,_:state))
    fiber=await ctx.plugin(CurrentSessionController)
    return ctx,ctx.get('sessionController'),fiber


@pytest.mark.asyncio
async def test_real_prompt_upload_selection_events_and_controller_unload(tmp_path):
    ctx,api,fiber=await mounted(tmp_path)
    notices=[]
    for name in ('added','removed','status','error','activity'):
        ctx.on('api-session/'+name,lambda *args,name=name:notices.append((name,args)))
    controller=AbortController()
    try:
        assert 'tools' not in CurrentSessionController.inject
        created=await api.create(dict(sessionId='actual',cwd=str(tmp_path)))
        assert created['sessionId']=='actual'
        agent=ctx.get('agents').get('actual')
        assert await ctx.get('fileUploads')._resolver['value']('actual') is agent
        upload=await ctx.get('fileUploads').upload(agent,dict(name='note.txt',data='aGVsbG8='),controller.signal)
        await api.selectModel(dict(sessionId='actual',provider='script',model='selected'))
        await api.prompt(dict(sessionId='actual',requestId='rpc',mode='queue',content=[dict(type='text',text='use the file'),dict(type='file',receiptId=upload['receiptId'])]),controller.signal)
        await asyncio.wait_for(agent.whenIdle(),3)
        assert ctx.get('fileUploads').resolve(agent,upload['receiptId']) is None
        state=ctx.get('sessionProjections').stateOf(agent.session,'modelSelection')
        assert state==dict(lastUsed=dict(provider='script',model='selected'),pending=None)
        inspected=await api.inspect('actual')
        assert inspected['meta'] is agent.session.header
        assert any(event['type']=='assistant/message' for event in inspected['events'])
        assert any(name=='status' and args==('actual',True) for name,args in notices)
        assert any(name=='activity' and args[0]=='actual' for name,args in notices)
        ctx.emit('agent/error',dict(agent=agent,error=RuntimeError('actual failure')))
        assert any(name=='error' and 'actual failure' in args[1] for name,args in notices)
        follow=api.follow(dict(address=dict(kind='session',sessionId='actual')),controller.signal)
        assert (await follow.__anext__())['cursor']==agent.session.seq-1
        control=api.control(controller.signal)
        assert (await control.__anext__())['value']['queues']['actual']==[]
        external=await ctx.get('agents').create(dict(sessionId='external',agentOptions=dict(provider='script',model='model'),meta=dict(cwd=str(tmp_path))))
        await fiber.dispose()
        assert ctx.get('sessionController') is None and ctx.get('sessionSkillCatalog') is None
        assert ctx.get('fileUploads')._resolver['value'] is None
        assert ctx.get('agents').get('actual') is None
        assert ctx.get('agents').get('external') is external.agent
        with pytest.raises(StopAsyncIteration): await follow.__anext__()
        for _ in range(20):
            try: await control.__anext__()
            except StopAsyncIteration: break
        else: pytest.fail('closed control did not drain within the accepted frame bound')
        count=len(notices);ctx.emit('agent/status',dict(agent=agent,status='running'))
        assert len(notices)==count
    finally:
        controller.abort();await ctx.fiber.dispose();unlock_owned(tmp_path)


@pytest.mark.asyncio
async def test_unload_closes_followers_before_waiting_for_admitted_promotion(tmp_path):
    ctx,api,fiber=await mounted(tmp_path)
    entered,release,disposed=asyncio.Event(),asyncio.Event(),[]
    async def activate(observed):
        entered.set();await release.wait();return dict(agent=object())
    api.agents.resolveObservedAgent=activate
    try:
        await api.create(dict(sessionId='actual',cwd=str(tmp_path)))
        signal=AbortController().signal
        follow=api.follow(dict(address=dict(kind='session',sessionId='actual')),signal)
        await follow.__anext__()
        waiting=asyncio.create_task(follow.__anext__())
        await asyncio.sleep(0)
        api.promote(SimpleNamespace(header=SimpleNamespace(id='actual'),dispose=lambda:disposed.append(True)))
        await entered.wait()
        teardown=asyncio.create_task(fiber.dispose())
        with pytest.raises(StopAsyncIteration): await asyncio.wait_for(waiting,2)
        assert not teardown.done() and not disposed
        release.set();await asyncio.wait_for(teardown,2)
        assert disposed==[True]
    finally:
        release.set();await ctx.fiber.dispose();unlock_owned(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome',('success','domain','throw','dispose-error'))
async def test_background_promotion_releases_observation_and_reports_domain_or_log(tmp_path,outcome):
    ctx,api,fiber=await mounted(tmp_path)
    disposed,failures,logs=[],[],[]
    ctx.on('api-session/error',lambda *args:failures.append(args))
    api.ctx.logger.error=logs.append
    async def activate(observation):
        if outcome=='throw': raise RuntimeError('activation crashed')
        return dict(error=RemoteError('gateway/internal','activation unavailable',{})) if outcome=='domain' else dict(agent=object())
    def dispose():
        disposed.append(True)
        if outcome=='dispose-error':raise RuntimeError('release failed')
    api.agents.resolveObservedAgent=activate
    try:
        api.promote(SimpleNamespace(header=SimpleNamespace(id='cold'),dispose=dispose))
        await api.drain()
        assert disposed==[True]
        assert failures==([('cold','activation unavailable')] if outcome=='domain' else [])
        if outcome in ('throw','dispose-error'):
            assert len(logs)==1 and ('activation crashed' if outcome=='throw' else 'release failed') in logs[0]
        else: assert logs==[]
    finally:
        await ctx.fiber.dispose();unlock_owned(tmp_path)
