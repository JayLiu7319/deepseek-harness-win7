"""Current journal, Assistant reconnect and control-stream acceptance."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.api.session_history_current import CurrentSessionHistory
from dsh.api.session_control_current import CurrentSessionControl
from dsh.cordis.plugin import Plugin
from dsh.core.abort import AbortController
from scripts.oracles.session_history_current_python import execute
from scripts.oracles.generate_agent_loop_current_cases import message
from scripts.session_format_oracle import json_equal
from tests.test_session_agents_current import api_harness


CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_history_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_history_control_contract(case):
    assert json_equal(execute(case), case['expected'])


@pytest.mark.asyncio
async def test_actual_agent_stream_reconnect_and_dense_committed_journal(tmp_path):
    ctx, api = await api_harness(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    async def stream(request):
        yield dict(type='text-delta', index=0, text='partial')
        entered.set()
        await release.wait()
        yield dict(type='text-delta', index=0, text=' complete')
        yield dict(type='finish', reason=dict(kind='stop'))
    ctx.get('llm').registerAdapter(['live'], SimpleNamespace(stream=stream))
    history = CurrentSessionHistory(ctx, lambda observed: observed.dispose())
    handle = await ctx.get('agents').create(dict(sessionId='actual', agentOptions=dict(provider='live', model='model'), meta=dict(cwd=str(tmp_path))))
    agent = handle.agent
    abort = AbortController()
    iterator = None
    try:
        agent.followup(message('work'))
        await asyncio.wait_for(entered.wait(), 3)
        iterator = history.follow(dict(address=dict(kind='session', sessionId='actual'), assistantStream=True), abort.signal)
        opening = await iterator.__anext__()
        active = opening['assistantStream']['activeAttempt']
        assert active['nextIndex'] == 1
        assert active['stream'][0]['texts'] == ['partial']
        assert opening['header']['version'] == 3 and opening['header']['isSeeded'] is False
        cursor, frames = opening['cursor'], []
        release.set()
        await asyncio.wait_for(agent.whenIdle(), 3)
        while True:
            frame = await asyncio.wait_for(iterator.__anext__(), 3)
            frames.append(frame)
            if frame['type'] == 'event' and frame['event']['type'] == 'turn/end':
                break
        durable = [frame['event'] for frame in frames if frame['type'] == 'event']
        assert [event['seq'] for event in durable] == list(range(cursor + 1, agent.session.seq))
        assistant = next(event for event in durable if event['type'] == 'assistant/message')
        assert assistant['data']['stream'][0]['texts'] == ['partial', ' complete']
        assert any(frame['type'] == 'assistant-stream' and frame['frame']['type'] == 'end' for frame in frames)
        assert not any(event['type'].startswith('chunkrow/') for event in durable)
        reconnect = history.follow(dict(address=dict(kind='session', sessionId='actual'), assistantStream=True), abort.signal)
        resumed = await reconnect.__anext__()
        assert 'activeAttempt' not in resumed['assistantStream']
        await reconnect.aclose()
    finally:
        release.set(); abort.abort()
        if iterator is not None:
            await iterator.aclose()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_cold_follow_promotion_replays_new_end_seed_without_gap(tmp_path):
    ctx, api = await api_harness(tmp_path)
    handle = await ctx.get('agents').create(dict(sessionId='cold', agentOptions=dict(provider='script', model='model'), meta=dict(cwd=str(tmp_path))))
    handle.agent.followup(message('stored'))
    await handle.agent.whenIdle()
    await handle.dispose()
    tasks = []
    def promote(observed):
        async def resume():
            try:
                found = await api.resolveObservedAgent(observed)
                assert 'agent' in found
            finally:
                observed.dispose()
        tasks.append(asyncio.ensure_future(resume()))
    history = CurrentSessionHistory(ctx, promote)
    abort = AbortController()
    iterator = history.follow(dict(address=dict(kind='session', sessionId='cold')), abort.signal)
    try:
        opening = await iterator.__anext__()
        assert ctx.get('agents').get('cold') is None and not tasks
        next_frame = await asyncio.wait_for(iterator.__anext__(), 3)
        await asyncio.gather(*tasks)
        assert next_frame['type'] == 'event' and next_frame['event']['seq'] == opening['cursor'] + 1
        assert next_frame['event']['type'] == 'session/end-seed'
        assert ctx.get('agents').get('cold') is not None
    finally:
        abort.abort(); await iterator.aclose()
        await asyncio.gather(*tasks, return_exceptions=True)
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_unload_wakes_history_and_drains_control_without_disposing_agent(tmp_path):
    ctx, api = await api_harness(tmp_path)
    holder = {}
    class Watching(Plugin):
        def apply(self, child):
            holder['history'] = CurrentSessionHistory(child, lambda observed: observed.dispose())
            holder['control'] = CurrentSessionControl(child)
    fiber = await ctx.plugin(Watching)
    agent = await api.ensureSession('live', str(tmp_path), False)
    abort = AbortController()
    history = holder['history'].follow(dict(address=dict(kind='session', sessionId='live')), abort.signal)
    control = holder['control'].control(abort.signal)
    try:
        await history.__anext__(); await control.__anext__()
        agent.inbox.append('next-turn', message('pending'))
        queued = await history.__anext__()
        assert queued['event']['type'] == 'agent/inbox/spliced'
        waiting = asyncio.ensure_future(history.__anext__())
        await asyncio.sleep(0)
        await fiber.dispose()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(waiting, 2)
        frames = [frame async for frame in control]
        assert [frame['type'] for frame in frames] == ['projection', 'queue']
        assert frames[-1]['items'][0]['message']['content'][0]['text'] == 'pending'
        assert ctx.get('agents').get('live') is agent
        assert not holder['history'].followers and not holder['control'].streams
    finally:
        abort.abort(); await history.aclose(); await control.aclose()
        await ctx.fiber.dispose()
