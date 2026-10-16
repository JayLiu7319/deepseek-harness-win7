"""Actual current Connection contribution over controlled query/FS/native seams."""
import asyncio
import json
from types import SimpleNamespace

from dsh.client.ui_deliverables_current import CurrentClientUiDeliverables
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.host.connection.current import CurrentHostConnection
from dsh.fs.fs_local import FsError
from dsh.typert.remote import RemoteError


async def run(test):
    ctx, controller, calls = Context(), AbortController(), []
    desktop=dict(name='serving host',available=not test.get('unavailable'),fileManager='explorer')
    def fail(stage):
        if test.get('failureStage')!=stage:return
        if test.get('remoteCode'):raise RemoteError(test['remoteCode'],'/private/host/path',{})
        raise FsError('/private/host/path',test.get('code','UNEXPECTED'))
    async def read(request,signal):
        calls.append(dict(op='read',request=request));fail('read')
        data=test.get('data',dict(turn=1,callId='call',files=[dict(path='报告.docx')]))
        return dict(session=test.get('header',dict(cwd='/child')),target=dict(type=test.get('eventType','deliverables/presented'),data=data))
    async def stat(scope,path,signal):
        calls.append(dict(op='stat',scope=scope,path=path));fail('stat')
        if test.get('abortDuring'):controller.abort(ValueError('cancelled'))
        return dict(absolutePath='/host/current.docx')
    async def resolve(path,options):
        calls.append(dict(op='resolve',path=path));fail('resolve')
        return object()
    def mapping(path):calls.append(dict(op='mapping',path=path));return None if test.get('unmapped') else '/process/current.docx'
    async def open_path(request,signal):calls.append(dict(op='open',request=request));fail('open')
    try:
        await ctx.plugin(CurrentSystemPrompt)
        ctx.set_service('sessionQuery',SimpleNamespace(readEvent=read))
        ctx.set_service('workspaceFiles',SimpleNamespace(stat=stat))
        ctx.set_service('sandboxPolicy',SimpleNamespace(workspaceRoot='/fallback'))
        ctx.set_service('fs',SimpleNamespace(resolve=resolve,processPathFromHostPath=mapping,processPath=lambda target:'/host/wrong' if test.get('wrongMapping') else '/host/current.docx'))
        ctx.set_service('sessionController',SimpleNamespace(workspaceDesktop=lambda:desktop,openWorkspacePath=open_path))
        connection=CurrentHostConnection(ctx,[],SimpleNamespace(isAuthenticated=lambda _:True))
        fiber=await ctx.plugin(CurrentClientUiDeliverables)
        if test.get('aborted'):controller.abort(ValueError('cancelled'))
        route=test.get('path','/api/present.open')
        query=test.get('query','?sessionId=child&seq=7&index=0')
        try:
            result=await connection.createSharedFetchHandler('/api').fetch(dict(url='http://localhost'+route+query,path=route,method=test.get('method','POST'),headers={},signal=controller.signal))
            value=dict(status=result['status'],headers=result['headers'],body=result['body'])
            if route=='/api/present.host' and value['status']==200:value['body']=json.loads(value['body'])
        except Exception as error:value=dict(error=str(error))
        await fiber.dispose()
        return dict(response=value,calls=calls,withdrawn=not any(path.startswith('/api/present.') for path in connection.fetch_routes))
    finally:await ctx.fiber.dispose()


def execute(test):return json.loads(json.dumps(asyncio.run(run(test))))
