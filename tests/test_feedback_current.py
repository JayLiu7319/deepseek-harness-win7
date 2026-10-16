"""Current canonical feedback, including actual cold writer ownership."""
import asyncio
import json
from pathlib import Path

import pytest

from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.feedback.message_current import CurrentMessageFeedback
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin
from dsh.session.jsonl_handle import JsonlSessionHandle
from scripts.oracles.agent_machine_current_python import execute
from scripts.oracles.session_format_python import decode

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/feedback_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_current_feedback_contract(case):
    result = execute(case, decode)
    assert result == case['expected']
    assert result['results'][0]['outcome'] == 'value'
    if case['case'] in ('feedback-current-live', 'feedback-current-cold'):
        created = result['results'][4 if case['case'].endswith('cold') else 3]
        assert created['outcome'] == 'value' and created['value']['ok']
        assert created['value']['value']['category'] == 'task-result'
        assert all('feedback' not in str(message) for message in result['final']['messages'])
    if 'concurrent-' in case['case']:
        values = next(row['value'] for row in result['results'] if isinstance(row.get('value'), list))
        assert values[0]['ok'] and values[1]['error']['code'] == 'version-conflict'


async def cold_fixture(tmp_path):
    ctx = Context()
    await ctx.plugin(CurrentSessionPlugin)
    await ctx.plugin(CurrentJsonlSessionPersistencePlugin, dict(root=str(tmp_path), compression='none'))
    fiber = await ctx.plugin(CurrentMessageFeedback, dict(maxNoteBytes=32))
    session = CurrentSession('cold')
    session.append('assistant/message', dict(stream=[], turn=1, step=1, message=dict(id='message', role='assistant',
        source=dict(kind='model', provider='test', model='test'), content=[dict(type='text', text='answer')])), surface_op='append')
    handle = await ctx.get('sessionPersistence').create(session.header.to_dict())
    await handle.append(session.snapshotEvents())
    await handle.flush()
    await handle.close()
    return ctx, fiber


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_abandon_cold_write_or_disposal(tmp_path, monkeypatch):
    ctx, fiber = await cold_fixture(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = JsonlSessionHandle.flush
    async def blocked(handle):
        entered.set()
        await release.wait()
        return await original(handle)
    monkeypatch.setattr(JsonlSessionHandle, 'flush', blocked)
    try:
        service = ctx.get('messageFeedback')
        pending = service.put(dict(sessionId='cold', messageId='message', rating='positive', ifVersion=None))
        await asyncio.wait_for(entered.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        disposing = asyncio.create_task(fiber.dispose())
        await asyncio.sleep(0)
        assert not disposing.done()
        release.set()
        await asyncio.wait_for(disposing, 2)
        handle = await ctx.get('sessionPersistence').open('cold', 'read')
        try:
            events = (await handle.read())['events']
            assert events[-1]['type'] == 'feedback/message-put'
            assert events[-1]['data']['item']['rating'] == 'positive'
            assert ctx.get('sessions').get('cold') is None
        finally:
            await handle.close()
    finally:
        release.set()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_cold_flush_failure_releases_write_handle(tmp_path, monkeypatch):
    ctx, fiber = await cold_fixture(tmp_path)
    failure = RuntimeError('injected flush failure')
    async def fail(handle):
        raise failure
    original = JsonlSessionHandle.flush
    monkeypatch.setattr(JsonlSessionHandle, 'flush', fail)
    try:
        with pytest.raises(RuntimeError) as caught:
            await ctx.get('messageFeedback').put(dict(sessionId='cold', messageId='message', rating='positive', ifVersion=None))
        assert caught.value is failure
        monkeypatch.setattr(JsonlSessionHandle, 'flush', original)
        handle = await asyncio.wait_for(ctx.get('sessionPersistence').open('cold', 'write'), 2)
        await handle.close()
    finally:
        await ctx.fiber.dispose()
