"""Upload receipt authority and real streaming HTTP regression tests."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.scope import create_scope
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.host.connection.current import CurrentHostConnection
from dsh.host.connection.http_current import current_bridge_handler
from dsh.host.file_upload_current import CurrentFileUploads, FILE_UPLOAD_PATH, handle_file_upload_http
from dsh.host.webserver.webserver import WebServerService
from dsh.interaction.commands_current import CurrentCommandRuntime
from dsh.typert.remote import RemoteError
from scripts.oracles.file_upload_current_python import execute

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/file_upload_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_original_upload_service_and_commands(case):
    result = execute(case)
    assert result == case['expected']
    rows = result['results']
    if case['case'] == 'upload-http':
        assert rows[0]['value']['body']['ok'] is True
        assert rows[0]['value']['mode'] == 'streaming'
        assert rows[0]['value']['body']['value']['file']['bytes'] == 6
    if case['case'] == 'upload-command-files':
        assert rows[2]['value']['result']['kind'] == 'success'
        assert len(result['invocations'][0]['attachments']) == 2
        assert rows[4]['value']['result']['kind'] == 'error'


async def harness(ctx, root):
    await ctx.plugin(CurrentSessionPlugin)
    await ctx.plugin(CurrentCommandRuntime)
    class Agent:
        pass
    agent = Agent()
    agent.id = 'one'
    agent.session = ctx.get('sessions').create('one')
    agent.ctx = create_scope(ctx, agent).ctx
    live = {'one': agent}
    ctx.set_service('agents', SimpleNamespace(get=lambda sid: live.get(sid)))
    store = CurrentLocalAttachmentStore(ctx, dict(dshHome=str(root)))
    connection = CurrentHostConnection(ctx, [], SimpleNamespace(is_authenticated=lambda _: True))
    fiber = await ctx.plugin(CurrentFileUploads)
    return agent, live, store, connection, fiber


def unlock_owned(root):
    for path in root.rglob('*'):
        if path.is_file():
            os.chmod(str(path), 0o600)


@pytest.mark.asyncio
async def test_actual_tcp_chunked_upload_bypasses_buffer_limit_and_withdraws_on_unload(tmp_path):
    ctx = Context()
    server = WebServerService(ctx, host='127.0.0.1', port=0)
    try:
        agent, live, store, connection, fiber = await harness(ctx, tmp_path)
        server.register('prefix', '/api', current_bridge_handler(connection, connection.createSharedFetchHandler('/api'), 8))
        await server.start()
        reader, writer = await asyncio.open_connection('127.0.0.1', server.listened_port)
        try:
            head = ('POST ' + FILE_UPLOAD_PATH + '?sessionId=one&name=large.bin HTTP/1.1\r\nHost: 127.0.0.1\r\n'
                    'Content-Type: application/octet-stream\r\nTransfer-Encoding: chunked\r\n\r\n')
            writer.write(head.encode('ascii'))
            for _ in range(32):
                writer.write(b'10000\r\n' + b'X' * 65536 + b'\r\n')
                await writer.drain()
            writer.write(b'0\r\n\r\n')
            await writer.drain()
            raw = await asyncio.wait_for(reader.read(), 5)
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass  # Preserve the primary read/write failure if the peer reset.
        headers, body = raw.split(b'\r\n\r\n', 1)
        assert headers.startswith(b'HTTP/1.1 200')
        receipt = json.loads(body.decode('utf-8'))
        assert receipt['ok'] is True and receipt['value']['file']['bytes'] == 2 * 1024 * 1024
        count = 0
        async for chunk in store.readFileStream(receipt['value']['file']):
            assert chunk == b'X' * len(chunk) and len(chunk) <= 65536
            count += len(chunk)
        assert count == 2 * 1024 * 1024
        assert ctx.get('fileUploads').resolve(agent, receipt['value']['receiptId']) == receipt['value']['file']
        await fiber.dispose()
        assert FILE_UPLOAD_PATH not in connection.fetch_routes
        dispose = ctx.get('commands').registerFileReceiptResolver(lambda *_: None)
        dispose()
    finally:
        await server.stop()
        await ctx.fiber.dispose()
        unlock_owned(tmp_path)


@pytest.mark.asyncio
async def test_disposed_agent_cannot_receive_receipt_after_storage_completes(tmp_path, monkeypatch):
    ctx = Context()
    try:
        agent, live, store, connection, fiber = await harness(ctx, tmp_path)
        entered, release = asyncio.Event(), asyncio.Event()
        real_save = store.admitEncodedFile
        async def save(input_data):
            value = await real_save(input_data)
            entered.set()
            await release.wait()
            return value
        monkeypatch.setattr(store, 'admitEncodedFile', save)
        uploads = ctx.get('fileUploads')
        task = asyncio.create_task(uploads.upload(agent, dict(data='YQ=='), AbortController().signal))
        try:
            await asyncio.wait_for(entered.wait(), 3)
            live.clear()
        finally:
            release.set()
        with pytest.raises(RemoteError) as caught:
            await task
        assert caught.value.code == 'session/not-found'
        assert list(uploads._staged.items()) == []
    finally:
        await ctx.fiber.dispose()
        unlock_owned(tmp_path)


@pytest.mark.asyncio
async def test_resolver_disposer_does_not_remove_a_replacement(tmp_path):
    ctx = Context()
    try:
        agent, live, store, connection, fiber = await harness(ctx, tmp_path)
        uploads = ctx.get('fileUploads')
        first = uploads.registerAgentResolver(lambda _: agent)
        first()
        second = uploads.registerAgentResolver(lambda _: agent)
        first()
        assert uploads._resolver['value'] is not None
        second()
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_http_validates_before_consuming_any_upload():
    class Service:
        async def uploadStream(self, _request):
            raise AssertionError('must not store')
    for request, status in [(dict(method='GET', headers={}, url='http://host'), 405),
        (dict(method='POST', headers={}, url='http://host'), 415),
        (dict(method='POST', headers={'content-type': 'application/octet-stream'}, url='http://host'), 400)]:
        assert (await handle_file_upload_http(Service(), request))['status'] == status
