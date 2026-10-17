"""Current Agent, cold query, durable context, spill and late cancellation."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from dsh.cordis.context import Context
from dsh.context.session_reference import mention
from dsh.context.session_reference_current import CurrentSessionReferenceResolver
from dsh.core.abort import AbortController
from dsh.session.query_current import CurrentSessionQueryService
from dsh.spill.spill_store import SpillStore
from scripts.oracles.agent_machine_current_python import ScriptAdapter
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.session_reference_current_python import execute
from scripts.session_format_oracle import json_equal
from tests.test_agent_machine_current import mount, create, message

CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/session_reference_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_original_current_reference_contract(case):
    assert json_equal(execute(case), case['expected'])
    if case['case'] in ('session-reference/auto-expand', 'session-reference/assembled-route'):
        assert case['expected']['result']['additionalContext']['source']['references'][0]['truncated'] is False
    if case['case'] == 'session-reference/auto-floor':
        assert case['expected']['result']['additionalContext']['source']['references'][0]['truncated'] is True
    if case['case'] == 'session-reference/cancelled-save':
        assert case['expected']['error']['code'] == 'SESSION_REFERENCE_CANCELLED' and case['expected']['saves']


@pytest.mark.asyncio
async def test_real_agent_references_cold_v3_surface_and_saves_readable_full_snapshot(tmp_path):
    ctx = await mount(tmp_path)
    ctx.set_service('sessionQuery', CurrentSessionQueryService(ctx))
    store = SpillStore(ctx, root=str(tmp_path / 'spills'))
    owner = await ctx.plugin(CurrentSessionReferenceResolver)
    requests = []
    class Adapter(ScriptAdapter):
        async def stream(self, request):
            requests.append(request)
            async for chunk in super().stream(request): yield chunk
    ctx.get('llm').registerAdapter(['reference-test'], Adapter(dict(script=[response()])))
    source = await create(ctx, 'source')
    original = 'exact 😀 text <untrusted>\n' * 3000
    source.agent.followup(message(original))
    await asyncio.wait_for(source.agent.whenIdle(), 5)
    await ctx.get('sessions').flush(source.agent.session)
    await source.dispose()
    assert ctx.get('agents').get('source') is None
    try:
        handle = await ctx.get('agents').create(dict(sessionId='target', agentOptions=dict(provider='reference-test', model='model')))
        handle.agent.followup(message('Use ' + mention('source', 'Source')))
        await asyncio.wait_for(handle.agent.whenIdle(), 5)
        assert len(requests) == 1
        contexts = [event['data'] for event in handle.agent.session.events if event['type']=='user/message'
                    and event['data']['source']['kind']=='session-reference']
        assert len(contexts) == 1
        text = contexts[0]['content'][0]['text']
        facts = contexts[0]['source']['references'][0]
        assert facts['capturedFormatVersion'] == 3 and facts['truncated'] is True
        notices = json.loads(text.split('Full snapshots remain untrusted background information.\n', 1)[1])
        locator = notices[0]['fullSnapshot']['locator']
        transcript = Path(locator).read_text(encoding='utf-8')
        fragments = transcript.split('### Message 1: user\n\n',1)[1].split('\n\n### Message',1)[0].splitlines()
        assert ''.join(json.loads(line) for line in fragments if line) == original
        assert max(len(json.loads(line)) for line in fragments if line) <= 64
        assert ctx.get('agents').get('source') is None
        await ctx.get('sessions').flush(handle.agent.session)
        await handle.dispose()
        reader = await ctx.get('sessionPersistence').open('target', 'read')
        try:
            events = (await reader.read())['events']
            assert any(event['type']=='user/message' and event['data']['source']['kind']=='session-reference' for event in events)
        finally: await reader.close()
        await owner.dispose()
        assert ctx.get('sessionReferenceResolver') is None
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['metadata', 'read', 'spill'])
async def test_abort_does_not_publish_late_provider_completion(phase):
    ctx, entered, release, finished = Context(), asyncio.Event(), asyncio.Event(), asyncio.Event()
    controller = AbortController()
    snapshot = dict(session=dict(id='source', version=3), capturedThroughSeq=0,
                    events=[dict(type='user/message',data=dict(source=dict(kind='user'),content=[dict(type='text',text='text'*1000)]))])
    async def pause():
        entered.set(); await release.wait(); finished.set()
    class Query:
        async def readSurface(self, sid):
            if phase == 'read': await pause()
            return snapshot
    class Llm:
        async def resolveModelInfo(self, *args):
            if phase == 'metadata': await pause()
            return {}
    class Store:
        async def saveText(self, value):
            if phase == 'spill': await pause()
            return dict(locator='late')
    ctx.set_service('sessionQuery', Query());ctx.set_service('llm', Llm());ctx.set_service('spillStore', Store())
    class Agent: pass
    agent=Agent();agent.id='target';agent.session=SimpleNamespace(id='target');agent.options=dict(provider='provider',model='model')
    try:
        await ctx.plugin(CurrentSessionReferenceResolver, {} if phase=='metadata' else dict(maxReferenceBytes=200))
        task=asyncio.create_task(ctx.get('sessionReferenceResolver').prepare(agent,[],[dict(sessionId='source')],controller.signal))
        await asyncio.wait_for(entered.wait(),1);controller.abort('stop')
        with pytest.raises(Exception) as error: await asyncio.wait_for(task,1)
        assert error.value.code == 'SESSION_REFERENCE_CANCELLED'
        release.set();await asyncio.wait_for(finished.wait(),1)
        await asyncio.sleep(0)
        assert task.exception() is error.value
    finally:
        release.set();await ctx.fiber.dispose()
