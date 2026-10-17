"""Current runner output semantics and actual current Agent frame ownership."""
import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dsh.boot.profile_boot import _AppReadyService
from dsh.bundle.headless.current import CurrentHeadlessRunner
from scripts.oracles.headless_current_python import execute
from tests.test_agent_machine_current import mount, ScriptAdapter


CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/headless_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_current_runner(case):
    assert execute(case) == case['expected']
    if case['case'] == 'headless/retry':
        assert case['expected']['err'] == 'dsh: reasoning:\nattempt1\ndsh: reasoning:\nattempt2\n'


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
async def test_real_current_agent_stream_is_rendered_and_subscription_released(tmp_path, cancelled):
    ctx = await mount(tmp_path)
    chunks = [dict(type='reasoning-delta', index=0, text='real reasoning'),
              dict(type='text-delta', index=1, text='real answer'), dict(type='finish', reason=dict(kind='stop'))]
    ctx.get('llm').registerAdapter(['headless-script'], ScriptAdapter(dict(script=[chunks])))
    ctx.set_service('agentDefaultModel', SimpleNamespace(current_selection=lambda: dict(provider='headless-script', model='m')))
    ready, done = _AppReadyService(), asyncio.get_running_loop().create_future()
    ctx.set_service('appReady', ready)
    ctx.set_service('appExit', lambda code: done.set_result(code))
    out, err, subjects = io.StringIO(), io.StringIO(), []
    ctx.on('agent/created', lambda payload: subjects.append(payload['agent']))
    def cancel(payload):
        if cancelled and payload['frame']['type'] == 'chunk' and payload['frame']['chunk']['type'] == 'reasoning-delta':
            payload['agent'].cancel()
    ctx.on('agent/assistant-stream', cancel)
    with patch('sys.stdout', out), patch('sys.stderr', err):
        try:
            await ctx.plugin(CurrentHeadlessRunner, dict(task='real task'))
            assert not done.done() and not subjects
            ready._commit()
            code = await asyncio.wait_for(done, 3)
            assert code == (1 if cancelled else 0)
            assert err.getvalue() == 'dsh: reasoning:\nreal reasoning\n'
            assert out.getvalue() == ('\n' if cancelled else 'real answer\n')
            assert len(subjects) == 1
            session = subjects[0].session
            assert not any(event['type'] == 'assistant/chunk' for event in session.events)
            reader = await ctx.get('sessionPersistence').open(session.id, 'read')
            try:
                events = (await reader.read())['events']
                assert events[-1]['type'] == 'turn/end'
                assert events[-1]['data']['reason']['kind'] == ('aborted' if cancelled else 'completed')
            finally:
                await reader.close()
            before = err.getvalue()
            ctx.emit('agent/assistant-stream', dict(agent=subjects[0], frame=dict(type='chunk', chunk=dict(type='reasoning-delta', text='late'))))
            assert err.getvalue() == before
        finally:
            await ctx.fiber.dispose()
