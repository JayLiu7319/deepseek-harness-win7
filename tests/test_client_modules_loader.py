import asyncio
import json

import pytest

from dsh.cordis.context import Context
from dsh.cordis.loader import Loader
from dsh.host.webserver.webserver import WebServerPlugin
from dsh.host.client_modules.registry import ClientModulesPlugin


def package(root, name):
    directory = root / 'node_modules' / name
    directory.mkdir(parents=True)
    (directory / 'package.json').write_text(json.dumps(dict(name=name, main='index.py',
        exports={'.': './index.py', './client': './client.js'}, dsh={'client': {'platform': 'web'}})), encoding='utf-8')
    (directory / 'index.py').write_text('def apply(ctx, config=None):\n    pass\n', encoding='utf-8')
    (directory / 'client.js').write_text('module.exports = {};', encoding='utf-8')
    return directory


async def settle():
    for _ in range(8):
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize('web_first', [False, True])
async def test_shell_carrier_without_listener_and_late_web_provider(tmp_path, web_first):
    package(tmp_path, '@fixture/desktop')
    ctx = Context()
    loader = Loader(ctx, {'baseUrl': str(tmp_path)})
    await loader.root.update([dict(id='desktop', name='@fixture/desktop')])
    if web_first:
        first = await ctx.plugin(WebServerPlugin, dict(port=0))
    fiber = await ctx.plugin(ClientModulesPlugin)
    try:
        modules = ctx.get('clientModules')
        if web_first:
            await settle()
            assert ctx.get('webServer').match('/plugins/x') is not None
            await first.dispose()
        assert ctx.get('webServer') is None
        url = modules.graph()['entries'][0]['url']
        request = dict(url='dsh-app://app' + url, method='GET')
        got = modules.fetchBundle(request)
        assert got['status'] == 200 and b'module.exports' in got['body']
        assert modules.fetchBundle(dict(request, method='HEAD')) == dict(got, body=None)
        assert modules.fetchBundle(dict(request, method='POST'))['status'] == 405
        assert modules.fetchBundle(dict(request, url='dsh-app://app/plugins/events'))['status'] == 404
        rows = []
        ctx.emit('webserver/index-inject', rows)
        assert rows == modules.boot_injections()
        web = await ctx.plugin(WebServerPlugin, dict(port=0))
        await settle()
        server = ctx.get('webServer')
        assert server.match('/plugins/x') is not None
        await web.dispose()
        assert ctx.get('clientModules') is modules
        assert modules.fetchBundle(request) == got
        await fiber.dispose()
        assert modules.closed and ctx.get('clientModules') is None
        rows = []
        ctx.emit('webserver/index-inject', rows)
        assert not rows
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_loader_order_duplicate_owners_unload_and_reactivation(tmp_path):
    for name in ('@fixture/z', '@fixture/a', '@fixture/inactive'):
        package(tmp_path, name)
    ctx = Context()
    loader = Loader(ctx, {'baseUrl': str(tmp_path)})
    await ctx.plugin(WebServerPlugin, config={'port': 0})
    await loader.root.update([dict(id='z', name='@fixture/z'), dict(id='a', name='@fixture/a'), dict(id='duplicate', name='@fixture/z')])
    plugin = await ctx.plugin(ClientModulesPlugin)
    modules = ctx.get('clientModules')
    try:
        initial = modules.graph()
        assert [row['id'] for row in initial['entries']] == ['@fixture/z', '@fixture/a']
        await loader.update('z', {'disabled': True})
        await settle()
        assert modules.graph() == initial
        await loader.update('duplicate', {'disabled': True})
        await settle()
        assert [row['id'] for row in modules.graph()['entries']] == ['@fixture/a']
        await loader.update('z', {'disabled': False})
        await settle()
        entries = modules.graph()['entries']
        assert [row['id'] for row in entries] == ['@fixture/a', '@fixture/z']
        assert entries[0]['rev'] == initial['entries'][1]['rev']
        assert entries[1]['rev'] != initial['entries'][0]['rev']
        await plugin.dispose()
        assert ctx.get('clientModules') is None and modules.closed
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_active_missing_bundle_fails_activation(tmp_path):
    directory = package(tmp_path, '@fixture/missing')
    (directory / 'client.js').unlink()
    ctx = Context()
    loader = Loader(ctx, {'baseUrl': str(tmp_path)})
    await ctx.plugin(WebServerPlugin, config={'port': 0})
    await loader.root.update([dict(id='missing', name='@fixture/missing')])
    try:
        with pytest.raises(Exception, match='client bundle'):
            await ctx.plugin(ClientModulesPlugin)
        assert ctx.get('clientModules') is None
    finally:
        await ctx.fiber.dispose()
