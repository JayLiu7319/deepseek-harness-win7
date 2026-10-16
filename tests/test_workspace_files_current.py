"""Current workspaceFiles wire values and real Session/FS read consumers."""
import asyncio
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.api.workspace_files_current import CurrentWorkspaceFiles
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.fs.fs_local import FsService,FsError
from dsh.fs.fs_sandbox import SandboxedFileSystem
from dsh.sandbox.sandbox_policy import SandboxPolicyService
from dsh.typert.current import CurrentTypertRegistry
from dsh.typert.remote import RemoteError
from dsh.typert.stores import field
from scripts.oracles.workspace_files_current_python import execute
from scripts.session_format_oracle import json_equal
from tests.test_session_agents_current import api_harness

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/workspace_files_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_workspace_preview_contract(case):
    assert json_equal(execute(case),case['expected'])


@pytest.mark.asyncio
async def test_actual_parent_child_and_cold_scopes_read_only_fs_and_related_resources(tmp_path):
    a,b=tmp_path/'a',tmp_path/'b';a.mkdir();b.mkdir()
    (a/'same.txt').write_bytes(b'parent\nsecond\n');(b/'same.txt').write_bytes(b'child\n')
    (a/'index.html').write_text('<html>',encoding='utf-8');(b/'style.css').write_text('body {}',encoding='utf-8')
    ctx,agents=await api_harness(tmp_path)
    await ctx.plugin(SandboxPolicyService,dict(mode='read-only',workspaceRoot=str(a)))
    await ctx.plugin(SandboxedFileSystem,dict(cwd=str(a)))
    fiber=await ctx.plugin(CurrentWorkspaceFiles,dict(maxBytes=32,maxFileBytes=100,maxLines=2,maxEntries=1))
    api=ctx.get('workspaceFiles');signal=AbortController().signal
    parent=await ctx.get('agents').create(dict(sessionId='parent',agentOptions=dict(provider='script',model='model'),meta=dict(cwd=str(a))))
    child=await ctx.get('agents').create(dict(sessionId='child',parentAgent=parent.agent,agentOptions=dict(provider='script',model='model'),meta=dict(cwd=str(b),parentSession='parent',origin='subagent',delegationDepth=1)))
    lookup=field(ctx.get('typert').lookups.get('workspaceFileScope'),'resolve')
    try:
        parent_scope,child_scope=await lookup('parent'),await lookup('child')
        assert (await api.read(parent_scope,'same.txt',{},signal))['text']=='parent\nsecond'
        assert (await api.read(child_scope,'same.txt',{},signal))['text']=='child'
        assert (await api.read(child_scope,str(a/'same.txt'),{},signal))['text']=='parent\nsecond'
        with pytest.raises(RemoteError) as refused:
            await api.list(child_scope,str(a),signal)
        assert refused.value.code=='workspace-file/outside-workspace'
        listing=await api.list(parent_scope,'.',signal)
        assert len(listing['entries'])==1 and listing['truncated'] is True
        related=await api.readRelated(parent_scope,'index.html','../b/style.css',signal)
        assert base64.b64decode(related['data'])==b'body {}'
        window=await api.readBytes(child_scope,'same.txt',dict(offset=1,length=2),signal)
        assert base64.b64decode(window['data'])==b'hi' and window['eof'] is False
        target=await ctx.get('fs').resolve(str(a/'same.txt'))
        with pytest.raises(FsError) as denied:
            await ctx.get('fs').writeText(target,'forbidden')
        assert denied.value.code=='FS_SANDBOX_DENIED'
        child.agent.session.append('session/title',dict(title='Child',messageSeqs=[],source=dict(kind='user')))
        await child.dispose();assert ctx.get('agents').get('child') is None
        cold_scope=await lookup('child')
        assert cold_scope==child_scope
        assert base64.b64decode((await api.readAll(cold_scope,'same.txt',signal))['data'])==b'child\n'
        assert ctx.get('agents').get('child') is None
        await fiber.dispose()
        assert not ctx.get('typert').lookups.has('workspaceFileScope')
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('ending',('abort','unload','success'))
async def test_actual_change_generation_during_slow_resolve(tmp_path,ending):
    ctx=Context();await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(CurrentTypertRegistry)
    fs=FsService(str(tmp_path));ctx.set_service('fs',fs);ctx.set_service('sandboxPolicy',SimpleNamespace(workspaceRoot=str(tmp_path)))
    fiber=await ctx.plugin(CurrentWorkspaceFiles);api=ctx.get('workspaceFiles')
    original=fs.resolve;root=await original(str(tmp_path));inside=await original(str(tmp_path/'inside'));outside=await original(str(tmp_path.parent/'outside'))
    entered,release=asyncio.Event(),asyncio.Event()
    async def slow(path,options=None):
        if path==str(tmp_path):
            entered.set();await release.wait()
            options['signal'].throwIfAborted();return root
        return await original(path,options)
    fs.resolve=slow;controller=AbortController();iterator=api.changes(dict(workspaceRoot=str(tmp_path)),controller.signal)
    first=asyncio.create_task(iterator.__anext__())
    try:
        await entered.wait()
        ctx.emit('fs/observed',outside,dict(kind='present',version='outside'))
        ctx.emit('fs/observed',inside,dict(kind='present',version='one'))
        if ending=='abort':controller.abort()
        if ending=='unload':await fiber.dispose()
        release.set()
        if ending=='success':
            assert await first==dict(kind='ready')
            assert await iterator.__anext__()==dict(kind='change',change=dict(absolutePath=fs.processPath(inside),version='one'))
            waiting=asyncio.create_task(iterator.__anext__());await asyncio.sleep(0)
            await fiber.dispose()
            with pytest.raises(StopAsyncIteration):await asyncio.wait_for(waiting,2)
        else:
            with pytest.raises(StopAsyncIteration):await first
        assert not api.feed.followers
    finally:
        release.set();controller.abort();await iterator.aclose();await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_actual_fs_text_refusal_and_complete_file_growth_cap(tmp_path):
    ctx=Context();await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(CurrentTypertRegistry)
    fs=FsService(str(tmp_path));ctx.set_service('fs',fs);ctx.set_service('sandboxPolicy',SimpleNamespace(workspaceRoot=str(tmp_path)))
    await ctx.plugin(CurrentWorkspaceFiles,dict(maxBytes=16,maxFileBytes=4));api=ctx.get('workspaceFiles');scope=dict(workspaceRoot=str(tmp_path));signal=AbortController().signal
    (tmp_path/'bad').write_bytes(b'\xff');(tmp_path/'zero.bin').write_bytes(b'\x00');(tmp_path/'growth').write_bytes(b'1234')
    original=fs.readByteRange
    async def growth(target,range,signal=None):
        with (tmp_path/'growth').open('ab') as stream:stream.write(b'5')
        return await original(target,range,signal)
    try:
        for path in ('bad','zero.bin'):
            with pytest.raises(RemoteError) as refused:await api.read(scope,path,{},signal)
            assert refused.value.code=='workspace-file/not-text'
        fs.readByteRange=growth
        with pytest.raises(RemoteError) as refused:await api.readAll(scope,'growth',signal)
        assert refused.value.code=='workspace-file/too-large'
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_change_iterator_return_releases_abort_listener_immediately(tmp_path):
    ctx=Context();await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(CurrentTypertRegistry)
    fs=FsService(str(tmp_path));ctx.set_service('fs',fs);ctx.set_service('sandboxPolicy',SimpleNamespace(workspaceRoot=str(tmp_path)))
    await ctx.plugin(CurrentWorkspaceFiles);api=ctx.get('workspaceFiles');controller=AbortController()
    iterator=api.changes(dict(workspaceRoot=str(tmp_path)),controller.signal)
    try:
        assert await iterator.__anext__()==dict(kind='ready')
        pending=asyncio.create_task(iterator.__anext__());await asyncio.sleep(0)
        target=await fs.resolve(str(tmp_path/'file'))
        ctx.emit('fs/observed',target,dict(kind='absent'))
        assert (await pending)['kind']=='change' and controller.signal._listeners
        await iterator.aclose()
        assert not controller.signal._listeners and not api.feed.followers
    finally:await iterator.aclose();await ctx.fiber.dispose()
