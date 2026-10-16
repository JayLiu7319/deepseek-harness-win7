"""Current Session delivery, durable inbox edits, receipts and actual Agent."""
import asyncio
import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.api.session_commands_current import CurrentSessionCommands, referenced_image
from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.agent_current import CurrentAgentPlugin
from dsh.core.agent_loop_current import CurrentAgentLoopPlugin
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.core.tools import ToolsPlugin
from dsh.host.connection.current import CurrentHostConnection
from dsh.host.file_upload_current import CurrentFileUploads
from dsh.interaction.commands_current import CurrentCommandRuntime
from dsh.llm.runtime_current import CurrentLlmRuntime
from dsh.session.projections import SessionProjectionsPlugin
from dsh.typert.remote import RemoteError
from scripts.oracles.file_upload_current_python import execute
from scripts.oracles.agent_machine_current_python import ScriptAdapter
from scripts.oracles.generate_agent_machine_current_cases import response

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/session_commands_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_original_session_delivery_contract(case):
    result = execute(case)
    assert result == case['expected']
    rows = result['results']
    if case['case'] in ('session-command-file-queue', 'session-command-mixed-order', 'session-command-file-steer'):
        assert rows[1] == dict(outcome='value', value=dict(accepted=True))
    if case['case'] == 'session-command-mixed-order':
        assert [part['type'] for part in rows[-1]['value']['nextTurn'][0]['content']] == ['file', 'text', 'image', 'file']
    if case['case'] == 'session-command-image-authorized':
        assert rows[1]['outcome'] == 'value' and base64.b64decode(rows[1]['value']['data']).startswith(b'\x89PNG')
    if case['case'] == 'session-command-retry-pending':
        assert rows[-2] == dict(outcome='value', value=dict(accepted=True))
        assert len(rows[-1]['value']['nextTurn']) == 1


async def mount(tmp_path):
    ctx = Context()
    for plugin in (CurrentLlmRuntime, CurrentSessionPlugin, SessionProjectionsPlugin, CurrentSystemPrompt, ToolsPlugin,
                   CurrentAgentPlugin, CurrentCommandRuntime):
        await ctx.plugin(plugin)
    await ctx.plugin(CurrentAgentLoopPlugin, dict(agents=[]))
    ctx.get('llm').registerAdapter(['script'], ScriptAdapter(dict(script=[response()])))
    store = CurrentLocalAttachmentStore(ctx, dict(dshHome=str(tmp_path)))
    CurrentHostConnection(ctx, [], SimpleNamespace(is_authenticated=lambda _: True))
    await ctx.plugin(CurrentFileUploads)
    handle = await ctx.get('agents').create(dict(sessionId='actual', agentOptions=dict(provider='script', model='model')))
    async def resolve(_sid):
        return dict(agent=handle.agent)
    lock = asyncio.Lock()
    async def serialize(_agent, operation):
        async with lock:
            return await operation()
    controller = CurrentSessionCommands(ctx, SimpleNamespace(resolveAgent=resolve,
        selectionFor=lambda _: SimpleNamespace(current=dict(provider='script', model='model')), serializeImageAdmission=serialize))
    return ctx, handle, store, controller


def unlock_owned(root):
    for parent, _, files in os.walk(str(root)):
        for name in files:
            os.chmod(os.path.join(parent, name), 0o600)


@pytest.mark.asyncio
async def test_actual_agent_logs_file_consumption_retires_receipt_and_retries_idempotently(tmp_path):
    ctx, handle, store, controller = await mount(tmp_path)
    requests = []
    ctx.on('llm/stream', lambda request, next: (requests.append(request), next())[1])
    try:
        uploads = ctx.get('fileUploads')
        receipt = await uploads.upload(handle.agent, dict(data='YWJj', name='readme.txt'), AbortController().signal)
        request = dict(sessionId='actual', requestId='req-1', mode='queue', content=[dict(type='file', receiptId=receipt['receiptId'])])
        assert await controller.prompt(request) == dict(accepted=True)
        await asyncio.wait_for(handle.agent.whenIdle(), 3)
        assert uploads.resolve(handle.agent, receipt['receiptId']) is None
        users = [event for event in handle.agent.session.snapshotEvents() if event['type'] == 'user/message']
        assert len(users) == 1 and users[0]['data']['content'][0]['attachment'] == receipt['file']
        assert users[0]['data']['source'] == dict(kind='user', rpcId='req-1')
        assert await controller.prompt(request) == dict(accepted=True)
        assert len(requests) == 1 and not handle.agent.inbox.hasPending
    finally:
        await ctx.fiber.dispose()
        unlock_owned(tmp_path)


@pytest.mark.asyncio
async def test_agent_disposal_during_admission_cannot_receive_message_or_binding(tmp_path, monkeypatch):
    ctx, handle, store, controller = await mount(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    original = store.admitPromptContent
    async def blocked(content):
        admitted = await original(content)
        entered.set()
        await release.wait()
        return admitted
    monkeypatch.setattr(store, 'admitPromptContent', blocked)
    task = None
    try:
        uploads = ctx.get('fileUploads')
        receipt = await uploads.upload(handle.agent, dict(data='YQ=='), AbortController().signal)
        task = asyncio.ensure_future(controller.prompt(dict(sessionId='actual', requestId='raced', mode='queue',
            content=[dict(type='file', receiptId=receipt['receiptId'])])))
        await asyncio.wait_for(entered.wait(), 3)
        await handle.dispose()
        release.set()
        with pytest.raises(RemoteError) as caught:
            await task
        assert caught.value.code == 'session/not-found'
        assert not any(event['type'] in ('agent/inbox/spliced', 'user/message') for event in handle.agent.session.snapshotEvents())
        assert handle.agent.session not in uploads._staged
    finally:
        release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await ctx.fiber.dispose()
        unlock_owned(tmp_path)


@pytest.mark.parametrize('event_type', ['assistant/message', 'assistant/attempt'])
def test_v3_compact_assistant_stream_authorizes_nested_image_reference(event_type):
    ref = dict(attachmentId='sha256:' + 'a' * 64)
    content = [dict(type='tool-result', content=[dict(type='image', attachment=ref)])]
    event = dict(type=event_type, data=dict(stream=[dict(type='chunk', time=1,
        chunk=dict(type='block-end', index=0, block=content[0]))]))
    assert referenced_image([event], ref['attachmentId']) is ref
    assert referenced_image([event], 'missing') is None
