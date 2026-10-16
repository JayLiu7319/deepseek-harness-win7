"""File handles at the actual LLM, Agent and metering boundaries."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.cordis.context import Context
from dsh.core.agent_current import CurrentAgentPlugin
from dsh.core.agent_loop_current import CurrentAgentLoopPlugin
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.core.tools import ToolsPlugin
from dsh.llm.runtime_current import CurrentLlmRuntime
from dsh.llm.token_meter_current import CurrentTokenMeterPlugin
from dsh.session.projections import SessionProjectionsPlugin
from scripts.oracles.llm_files_current_python import execute

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/llm_files_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_original_llm_file_projection(case):
    result = execute(case)
    assert result == case['expected']
    if case['operation'] == 'runtime' and not case.get('shortCircuit') and not any(step.get('mapError') for step in case['steps']):
        assert len(result['requests']) == len(case['steps'])
        assert all(chunks == [dict(type='text', text='accepted')] for chunks in result['chunks'])


@pytest.mark.asyncio
async def test_actual_agent_keeps_file_history_but_dispatches_current_read_path_and_prices_it(tmp_path):
    ctx = Context()
    handle = None
    requests, intercepted, errors = [], [], []
    world = dict(prefix='/execution/')
    try:
        for plugin in (CurrentLlmRuntime, CurrentSessionPlugin, SessionProjectionsPlugin,
                       CurrentSystemPrompt, ToolsPlugin, CurrentAgentPlugin, CurrentTokenMeterPlugin):
            await ctx.plugin(plugin)
        store = CurrentLocalAttachmentStore(ctx, {'dshHome': str(tmp_path)})
        ctx.set_service('fs', SimpleNamespace(processPathFromHostPath=lambda path: world['prefix'] + os.path.basename(path)))
        ref = await store.admitEncodedFile(dict(data='dmVyYmF0aW0=', name='notes.txt'))
        class Adapter:
            async def resolve_model(self, provider, model, signal=None):
                return dict(provider=provider, id=model, name=model, inputModalities=['text'])
            async def stream(self, request):
                requests.append(request)
                yield dict(type='text-delta', index=0, text='ok')
                yield dict(type='finish', reason=dict(kind='stop'))
        ctx.get('llm').registerAdapter(['files'], Adapter())
        def observe(request, next_fn):
            intercepted.append(request)
            return next_fn()
        ctx.on('llm/stream', observe)
        ctx.on('agent/error', lambda payload: errors.append(payload['error']))
        await ctx.plugin(CurrentAgentLoopPlugin, dict(agents=[]))
        handle = await ctx.get('agents').create(dict(sessionId='actual-files', agentOptions=dict(provider='files', model='model')))
        agent = handle.agent
        agent.followup(dict(role='user', id='file-message', source=dict(kind='user'), content=[dict(type='file', attachment=ref)]))
        await asyncio.wait_for(agent.whenIdle(), 5)
        assert errors == [] and len(requests) == 1
        durable = next(message for message in agent.session.deriveMessages() if message['id'] == 'file-message')
        assert durable['content'] == [dict(type='file', attachment=ref)]
        incoming = next(message for message in intercepted[0]['messages'] if message['id'] == 'file-message')
        outgoing = next(message for message in requests[0]['messages'] if message['id'] == 'file-message')
        assert incoming['content'][0]['type'] == 'file'
        assert outgoing['content'][0]['type'] == 'text'
        assert '"/execution/notes.txt"' in outgoing['content'][0]['text']
        assert 'include this saved path in the delegation prompt' in outgoing['content'][0]['text']
        assert b''.join([chunk async for chunk in store.readFileStream(ref)]) == b'verbatim'
        revision = len(agent.session.events)
        meter = ctx.get('tokenMeter')
        before = meter.measure(agent.session)
        world['prefix'] = '/new-world/' + 'long-path/' * 50
        after = meter.measure(agent.session)
        assert after['surfaceTokens'] > before['surfaceTokens']
        assert len(agent.session.events) == revision
        assert durable['content'][0]['type'] == 'file'
    finally:
        if handle is not None:
            await handle.dispose()
        await ctx.fiber.dispose()
        for path in tmp_path.rglob('*'):
            if path.is_file():
                os.chmod(str(path), 0o600)
