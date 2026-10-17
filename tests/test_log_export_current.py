"""Actual v3 read handles, canonical ZIP contents and export ownership."""
import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest

from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.core.abort import AbortController
from dsh.interaction.commands_current import CurrentCommandRuntime
from dsh.host.connection.current import CurrentHostConnection
from dsh.session.log_export_current import (
    CurrentSessionLogExportPlugin, archive, read_session_log_text, serialize_session_log)
from scripts.oracles.log_export_current_python import execute
from tests.test_agent_machine_current import mount, create

CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/log_export_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_frozen_original_export_observation(case):
    assert execute(case) == case['expected']


async def mounted(tmp_path):
    ctx = await mount(tmp_path)
    await ctx.plugin(CurrentCommandRuntime)
    await ctx.plugin(CurrentLocalAttachmentStore, dict(root=str(tmp_path / 'attachments')))
    ctx.set_service('connection', CurrentHostConnection(ctx, [], SimpleNamespace(is_authenticated=lambda _: True)))
    routes = ctx.get('connection').fetch_routes
    ctx.set_service('sessionQuery', SimpleNamespace())
    fiber = await ctx.plugin(CurrentSessionLogExportPlugin)
    return ctx, routes, fiber


@pytest.mark.asyncio
@pytest.mark.parametrize('cold', [False, True])
async def test_real_current_agent_log_and_generic_file_are_read_back_from_exported_zip(tmp_path, cold):
    ctx, routes, fiber = await mounted(tmp_path)
    try:
        result = await create(ctx, 'root')
        agent = result.agent
        ref = await ctx.get('attachments').saveFile(dict(name='汉字.txt', mediaType='text/plain', data=b'owned file'))
        agent.followup(dict(id='prompt', role='user', source=dict(kind='user'),
                            content=[dict(type='text', text='task'), dict(type='file', attachment=ref)]))
        await agent.whenIdle()
        expected = serialize_session_log(agent.session.header, list(agent.session.events))
        if cold:
            await result.dispose()
        if not cold:
            await ctx.get('sessions').flush(agent.session)
        assert await read_session_log_text(ctx.get('sessionPersistence'), 'root') == expected
        route = routes['/api/session.export']
        assert route['requestBody'] == 'buffered'
        response = await route['fetch'](dict(method='GET', url='http://localhost/api/session.export?sessionId=root'))
        assert response['status'] == 200
        data = b''.join([chunk async for chunk in response['body']])
        with zipfile.ZipFile(io.BytesIO(data)) as zipped:
            names = zipped.namelist()
            assert names[0] == 'session.v3.jsonl'
            assert zipped.read(names[0]).decode('utf-8') == expected
            assert len(names) == 2 and names[1].endswith('/汉字.txt')
            assert zipped.read(names[1]) == b'owned file'
        await fiber.dispose()
        assert not routes
        assert not any(row['name'] == 'export' for row in ctx.get('commands').list(agent))
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['GET', 'HEAD'])
@pytest.mark.parametrize('query,status', [('sessionId=absent', 404), ('', 400), ('sessionId=root&includeDescendants=invalid', 400)])
async def test_http_failures_and_head_have_original_status_and_no_leaked_body(tmp_path, method, query, status):
    ctx, routes, _ = await mounted(tmp_path)
    try:
        value = await routes['/api/session.export']['fetch'](dict(method=method, url='http://localhost/api/session.export?' + query))
        assert value['status'] == status
        assert value['headers']['content-type'] == 'text/plain;charset=UTF-8'
        assert (value['body'] is None) == (method == 'HEAD')
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_read_closes_handle_after_abort_and_does_not_swallow_other_open_errors(tmp_path):
    ctx = await mount(tmp_path)
    try:
        result = await create(ctx, 'root')
        await ctx.get('sessions').flush(result.agent.session)
        assert await read_session_log_text(ctx.get('sessionPersistence'), 'absent') is None
        assert json.loads((await read_session_log_text(ctx.get('sessionPersistence'), 'root')).splitlines()[0])['version'] == 3
        controller = AbortController()
        signal = controller.signal
        controller.abort(RuntimeError('owned abort'))
        with pytest.raises(RuntimeError, match='owned abort'):
            await read_session_log_text(ctx.get('sessionPersistence'), 'root', signal)
        # A failed export read leaves the active Agent's writer ownership intact.
        assert result.agent.session is ctx.get('sessions').get('root')
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('abort', [False, True])
async def test_compressor_pulls_file_chunks_incrementally_and_releases_after_consumer_stops(abort):
    controller = AbortController()
    signal = controller.signal
    reads = []
    closed = []
    async def read(ref, signal):
        try:
            for index in range(100):
                reads.append(index)
                yield bytes([index]) * 65536
        finally:
            closed.append(True)
    services = dict(attachments=SimpleNamespace(readFileStream=read))
    content = json.dumps(dict(data=dict(content=[dict(type='file', attachment=dict(attachmentId='sha256:abcd', name='large'))]))) + '\n'
    stream = archive(SimpleNamespace(get=services.get), content, 'root', False, 6, signal)
    while not reads:
        await stream.__anext__()
    assert reads == [0]
    if abort:
        controller.abort(RuntimeError('consumer stopped'))
        with pytest.raises(RuntimeError, match='consumer stopped'):
            await stream.__anext__()
    else:
        await stream.aclose()
    assert closed == [True]
    count = len(reads)
    await asyncio.sleep(0)
    assert len(reads) == count
    await stream.aclose()
