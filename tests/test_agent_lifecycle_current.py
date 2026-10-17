"""v3 writer publication and teardown using real registries, scopes and JSONL."""
import asyncio
from types import SimpleNamespace

import pytest

from dsh.cordis.context import Context
from dsh.cordis.errors import AggregateError
from dsh.core.abort import AbortController
from dsh.core.agent import AgentPlugin,AgentOptions
from dsh.core.agent_lifecycle_current import CurrentAgentLifecyclePlugin
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.system_prompt import SystemPrompt
from dsh.core.tools import ToolsPlugin
from dsh.llm.llm_service import LlmRuntime
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin
from dsh.session.persistence import SessionAlreadyOwnedError,SessionPersistenceNotFoundError
from dsh.session.projections import SessionProjectionsPlugin


async def mount(tmp_path,compression='none'):
    ctx=Context()
    for plugin in (LlmRuntime,CurrentSessionPlugin,SessionProjectionsPlugin,SystemPrompt,ToolsPlugin,AgentPlugin):
        await ctx.plugin(plugin)
    await ctx.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=str(tmp_path/'sessions'),compression=compression))
    fiber=await ctx.plugin(CurrentAgentLifecyclePlugin,dict(agents=[]))
    return ctx,fiber,ctx.get('agentLoop'),ctx.get('sessionPersistence')


def header(sid='saved'):
    return dict(version=3,id=sid,createdAt=1,isSeeded=False)


def event(seq=0,kind='turn/start'):
    return dict(type=kind,seq=seq,time=seq+1,data=dict(turn=1,**(dict(reason=dict(kind='completed')) if kind=='turn/end' else {})))


async def stored(p,sid='saved'):
    h=await p.open(sid,'read')
    try:return (await h.read())['events']
    finally:await h.close()


@pytest.mark.parametrize('compression',['none','zstd'])
@pytest.mark.asyncio
async def test_create_seed_and_setup_suffix_are_stored_before_publication(tmp_path,compression):
    ctx,fiber,factory,p=await mount(tmp_path,compression);seen=[];observed=asyncio.Event()
    async def created(session):
        seen.append([e['type'] for e in await stored(p,'fresh')])
        observed.set()
    ctx.on('session/created',created)
    def setup(scope,agent):
        assert ctx.get('sessions').get('fresh') is None
        assert agent.session.id=='fresh'
        agent.session.append('session/title',dict(title='setup title',source='manual'))
    try:
        handle=await ctx.get('agents').create(dict(sessionId='fresh',seed=[event(),event(1,'turn/end')],setup=setup))
        await asyncio.wait_for(observed.wait(),2)
        expected=['turn/start','turn/end','session/end-seed','session/title']
        assert [e['type'] for e in await stored(p,'fresh')]==expected
        assert seen==[expected]
        handle.agent.session.append('session/title',dict(title='after publication',source='manual'))
        await handle.dispose()
        assert [e['type'] for e in await stored(p,'fresh')]==expected+['session/title']
        assert not p.tracker.writers and ctx.get('sessions').get('fresh') is None
    finally:await ctx.fiber.dispose()


@pytest.mark.parametrize('phase',['options','setup','commit','publication'])
@pytest.mark.asyncio
async def test_fresh_failure_releases_lazy_writer_without_artifact_and_preserves_primary(tmp_path,phase):
    ctx,fiber,factory,p=await mount(tmp_path);primary=RuntimeError('primary')
    def fail(*args):raise primary
    setup=None;options=None;withdraw=None
    if phase=='setup':setup=fail
    if phase=='commit':setup=lambda scope:SimpleNamespace(commit=fail)
    if phase=='options':options=AgentOptions(max_tokens=0)
    if phase=='publication':withdraw=ctx.on('agent/session-start',fail)
    try:
        with pytest.raises((RuntimeError,TypeError)) as caught:
            await factory.create_agent('fresh',options=options,setup=setup)
        if phase!='options':assert caught.value is primary
        assert not ctx.get('sessions').list() and not ctx.get('agents').list() and not p.tracker.writers
        assert await p.stat('fresh') is None
        if withdraw:withdraw()
        h=await factory.create_agent('fresh');await h.dispose()
    finally:await ctx.fiber.dispose()


@pytest.mark.parametrize('compression',['none','zstd'])
@pytest.mark.asyncio
async def test_resume_repairs_through_owned_writer_before_setup_and_appends_marker(tmp_path,compression):
    ctx,fiber,factory,p=await mount(tmp_path,compression)
    writer=await p.create(header());await writer.append([event()]);await writer.close()
    entered=[]
    async def setup(scope,agent):
        assert not ctx.get('sessions').list()
        entered.extend(e['type'] for e in await stored(p))
        assert agent.session.events[1]['data']['reason']['kind']=='interrupted'
    try:
        h=await ctx.get('agents').resume(dict(resumeSessionId='saved',setup=setup))
        assert entered==['turn/start','turn/end','session/end-seed']
        with pytest.raises(SessionAlreadyOwnedError):await p.open('saved','write')
        await h.dispose()
        again=await factory.resume('saved');await again.dispose()
        assert [e['type'] for e in await stored(p)]==entered
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_seed_fork_inherited_cut_is_owned_and_persisted(tmp_path):
    ctx,fiber,factory,p=await mount(tmp_path)
    try:
        seed=[event(),event(1,'turn/end')]
        h=await factory.create_agent('child',meta=dict(isSeeded=True,parentSession='parent'),seed=seed,inherited_event_count=2)
        assert h.agent.session.inheritedEventCount==2
        await h.dispose()
        reader=await p.open('child','read')
        assert reader.inheritedEventCount==2
        assert (await reader.read())['events'][2]['data']==dict(inherited=True)
        await reader.close()
    finally:await ctx.fiber.dispose()


@pytest.mark.parametrize('phase',['create','open','read','setup'])
@pytest.mark.parametrize('source',['caller','owner','factory','observer'])
@pytest.mark.asyncio
async def test_abort_unpublished_lifetimes_and_close_late_handle_once(tmp_path,phase,source,monkeypatch):
    ctx,fiber,factory,p=await mount(tmp_path)
    if phase in ('open','read'):
        writer=await p.create(header());await writer.flush();await writer.close()
    owner=await ctx.plugin(lambda scope:None)
    started=asyncio.Event();late=asyncio.get_running_loop().create_future();controller=AbortController();closed=[]
    async def close():closed.append(1)
    abandoned=SimpleNamespace(close=close)
    async def blocked(*args,**kwargs):started.set();await late;return abandoned
    setup=None
    if phase in ('create','open'):monkeypatch.setattr(p,phase,blocked)
    if phase=='read':
        original=p.open
        async def opened(*args,**kwargs):
            h=await original(*args,**kwargs)
            async def read(*args,**kwargs):started.set();await late;return dict(eventState='detached',events=[])
            h.read=read
            return h
        monkeypatch.setattr(p,'open',opened)
    if phase=='setup':
        async def setup(scope):started.set();await late
    method=factory.resume if phase in ('open','read') else factory.create_agent
    job=asyncio.create_task(method('saved',setup=setup,signal=controller.signal,owner_ctx=owner.ctx))
    await asyncio.wait_for(started.wait(),2)
    try:
        if source=='caller':controller.abort(RuntimeError('caller stopped'))
        elif source=='owner':await asyncio.wait_for(owner.dispose(),2)
        elif source=='factory':await asyncio.wait_for(factory.teardown(),2)
        else:job.cancel()
        with pytest.raises((RuntimeError,asyncio.CancelledError)):await asyncio.wait_for(job,2)
        assert ctx.get('agents').get('saved') is None and ctx.get('sessions').get('saved') is None
        late.set_result(None)
        for _ in range(12):await asyncio.sleep(0)
        if phase in ('create','open'):assert closed==[1]
        assert not p.tracker.writers
    finally:
        if not late.done():late.set_result(None)
        await asyncio.gather(job,return_exceptions=True)
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_disposal_joins_handle_close_before_registry_detach_and_propagates_failure(tmp_path,monkeypatch):
    ctx,fiber,factory,p=await mount(tmp_path);h=await factory.create_agent('fresh')
    tx=next(iter(factory._transactions));writer=tx.stored['handle'];original=writer.close
    entered=asyncio.Event();release=asyncio.Event();failure=RuntimeError('durability failed');calls=[]
    async def close():
        calls.append(1);entered.set();await release.wait();await original();raise failure
    monkeypatch.setattr(writer,'close',close)
    first=asyncio.create_task(h.dispose());second=asyncio.create_task(h.dispose())
    await asyncio.wait_for(entered.wait(),2)
    assert ctx.get('agents').get('fresh') is h.agent and ctx.get('sessions').get('fresh') is h.agent.session
    release.set()
    try:
        results=await asyncio.gather(first,second,return_exceptions=True)
        assert results==[failure,failure] and calls==[1]
        assert ctx.get('agents').get('fresh') is None and ctx.get('sessions').get('fresh') is None
        assert not p.tracker.writers
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_teardown_aggregates_scope_and_durability_failures_without_registry_leak(tmp_path,monkeypatch):
    ctx,fiber,factory,p=await mount(tmp_path);h=await factory.create_agent('fresh')
    tx=next(iter(factory._transactions));writer=tx.stored['handle'];scope_dispose=tx.scope.dispose;writer_close=writer.close
    first=RuntimeError('scope');second=RuntimeError('write')
    async def scope():await scope_dispose();raise first
    async def close():await writer_close();raise second
    monkeypatch.setattr(tx.scope,'dispose',scope);monkeypatch.setattr(writer,'close',close)
    try:
        with pytest.raises(AggregateError) as caught:await h.dispose()
        assert caught.value.errors==[first,second] and not ctx.get('agents').list() and not ctx.get('sessions').list()
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_retirement_joins_only_its_admitted_checkpoint_flush(tmp_path, caplog):
    from dsh.storage.hub import StoragePlugin
    from dsh.storage.plugins import StorageJsonPlugin, StorageDomainPlugin
    from dsh.session.projection_cache_current import CurrentSessionProjectionCachePlugin
    ctx, fiber, factory, persistence = await mount(tmp_path)
    for plugin, config in ((StoragePlugin, {}),
                           (StorageJsonPlugin, dict(root=str(tmp_path / 'storage'))),
                           (StorageDomainPlugin, dict(backend='json')),
                           (CurrentSessionProjectionCachePlugin, dict(writeEveryEvents=100, writeIntervalMs=60000))):
        await ctx.plugin(plugin, config)
    cache = ctx.get('sessionProjectionCache')
    first = await factory.create_agent('first')
    other = await factory.create_agent('other')
    await cache.drain(first.agent.session)
    await cache.drain(other.agent.session)
    entered = {name: asyncio.Event() for name in ('first', 'other')}
    release = {name: asyncio.Event() for name in ('first', 'other')}
    async def barrier(session):
        entered[session.id].set()
        await release[session.id].wait()
    remove = ctx.on('session/flush', barrier)
    writes = [cache.write(handle.agent.session) for handle in (first, other)]
    closing = None
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 2)
        closing = asyncio.create_task(first.dispose())
        await asyncio.sleep(0)
        assert not closing.done()
        assert persistence.tracker.writers['first']._closing is None
        release['first'].set()
        await asyncio.wait_for(closing, 2)
        assert not writes[1].done()
        assert ctx.get('sessions').get('first') is None
        assert ctx.get('sessions').get('other') is other.agent.session
        assert 'Checkpoint write failed' not in caplog.text
    finally:
        for event in release.values():
            event.set()
        await asyncio.gather(*writes)
        if closing is not None:
            await closing
        remove()
        await other.dispose()
        await ctx.fiber.dispose()


@pytest.mark.parametrize('kind',['absent','ordinary-file-not-found','corrupt','backend-failure'])
@pytest.mark.asyncio
async def test_configured_restore_only_creates_after_typed_absence(tmp_path,kind):
    from dsh.session.persistence import SessionPersistenceCorruptionError
    ctx,fiber,factory,p=await mount(tmp_path);seen=[]
    failure={'absent':SessionPersistenceNotFoundError('configured'),
             'ordinary-file-not-found':FileNotFoundError('not a typed absence'),
             'corrupt':SessionPersistenceCorruptionError('bad'),
             'backend-failure':RuntimeError('io')}[kind]
    async def opened(*args,**kwargs):raise failure
    ctx.on('agent-loop/config-start-failed',lambda payload:seen.append(payload))
    try:
        await factory._configured.restore(dict(id='entry',sessionId='configured'),AgentOptions(),{},SimpleNamespace(open=opened))
        if kind=='absent':
            assert ctx.get('agents').get('configured') is not None and not seen
        else:
            assert ctx.get('agents').get('configured') is None
            assert len(seen)==1 and seen[0]['error'] is failure
    finally:await ctx.fiber.dispose()
