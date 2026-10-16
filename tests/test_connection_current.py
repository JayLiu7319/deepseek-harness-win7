"""Carrier-neutral current Connection and actual streaming socket lifetimes."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.cordis.context import Context
from dsh.host.connection.current import CurrentConnectionPlugin, CurrentHostConnection
from dsh.host.connection.http_current import current_bridge_handler
from dsh.host.webserver.webserver import WebServerService
from scripts.oracles.agent_machine_current_python import execute
from scripts.oracles.session_format_python import decode

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/connection_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_current_connection_contract(case):
    result = execute(case, decode)
    assert result == case['expected']
    if case['case'] == 'connection-current-headless':
        assert result['results'][0]['value'] == dict(available=True, webServer=False)
    if case['case'].startswith('connection-current-http-'):
        assert result['results'][0]['outcome'] == 'value'
        if 'streaming' in case['case']:
            assert result['results'][0]['value']['observed']['received'] == '123456789abcdef'


@pytest.mark.asyncio
async def test_late_web_carrier_is_reversible_and_injects_recovery():
    ctx = Context()
    records = {}
    def modify(key, mutator):
        value = mutator(records.get(key))
        if value is not None:
            records[key] = value
        return records.get(key)
    ctx.set_service('credentials', SimpleNamespace(modify_record=modify))
    fiber = await ctx.plugin(CurrentConnectionPlugin, dict(recovery=dict(backoffFactor=1)))
    server = WebServerService(ctx, host='127.0.0.1', port=0)
    try:
        assert ctx.get('connection') is not None
        assert server.match('/api/test') is None
        ctx.set_service('webServer', server)
        async def mounted():
            while server.match('/api/test') is None:
                await asyncio.sleep(0)
        await asyncio.wait_for(mounted(), 1)
        table = []
        ctx.emit('webserver/index-inject', table)
        assert table[0]['name'] == '__DSH_CONNECTION_RECOVERY__'
        assert table[0]['value']['backoffFactor'] == 1
        await fiber.dispose()
        assert server.match('/api/test') is None and ctx.get('connection') is None
        table = []
        ctx.emit('webserver/index-inject', table)
        assert table == []
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('consume', [False, True])
async def test_disconnect_aborts_streaming_body_without_competing_reads(consume):
    ctx = Context()
    server = WebServerService(ctx, host='127.0.0.1', port=0)
    connection = CurrentHostConnection(ctx, [], SimpleNamespace(is_authenticated=lambda _: True))
    entered, stopped = asyncio.Event(), asyncio.Event()
    async def fetch(request):
        entered.set()
        try:
            if consume:
                async for chunk in request['body']:
                    assert chunk
            else:
                await request['signal'].wait_aborted()
        except asyncio.IncompleteReadError:
            pass
        assert request['signal'].aborted
        stopped.set()
        return dict(status=200, body='done')
    connection.fetch.register(dict(path='/api/upload', methods=['POST'], requestBody='streaming', fetch=fetch))
    server.register('prefix', '/api', current_bridge_handler(connection, connection.createSharedFetchHandler('/api'), 1))
    await server.start()
    reader, writer = await asyncio.open_connection('127.0.0.1', server.listened_port)
    try:
        writer.write(b'POST /api/upload HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 100000\r\n\r\nunread bytes')
        await writer.drain()
        await asyncio.wait_for(entered.wait(), 1)
        writer.close()
        await writer.wait_closed()
        await asyncio.wait_for(stopped.wait(), 1)
    finally:
        writer.close()
        await server.stop()
        await ctx.fiber.dispose()
