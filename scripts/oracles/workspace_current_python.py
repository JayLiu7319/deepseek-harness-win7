"""Actual Workspace registry over durable domains and snapshot-only persistence."""
import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

from dsh.cordis.context import Context
from dsh.storage.hub import Storage
from dsh.workspace.current import CurrentWorkspacePlugin, fully_qualified_workspace_path, default_workspace_title


async def run(test):
    if test.get('operation')=='path':
        return dict(qualified=fully_qualified_workspace_path(test['path'],test['platform']),title=default_workspace_title(test['path'],test['platform']))
    with tempfile.TemporaryDirectory(prefix='rc3-workspace-') as directory:
        root=Path(directory);(root/'a').mkdir();(root/'b').mkdir()
        headers=[dict(version=3,id='one',createdAt=1,isSeeded=False,cwd=str(root/'a'))]
        contexts=[];results=[]
        async def listed():return [dict(header=header,revision='revision-'+header['id']) for header in headers]
        async def boot():
            ctx=Context();contexts.append(ctx);Storage(ctx,root_dir=str(root/'storage'))
            ctx.set_service('sessionPersistence',SimpleNamespace(list=listed))
            await ctx.plugin(CurrentWorkspacePlugin)
            return ctx,ctx.get('workspaceRegistry')
        ctx,registry=await boot()
        def snapshot():
            return dict(items=[dict(path=Path(item.path).name,title=item.title,sessionIds=list(item.sessionIds)) for item in registry.list()],archived=registry.archivedSessionIds)
        try:
            for action in test['actions']:
                op=action['op']
                if op=='reopen':await ctx.fiber.dispose();ctx,registry=await boot()
                elif op=='create':await registry.create(str(root/action['path']))
                elif op=='headers':headers[:]=[dict(version=3,id=row['id'],createdAt=row.get('time',1),isSeeded=False,cwd=str(root/row['path'])) for row in action['headers']]
                elif op=='archive':await registry.archiveSession(action['id'])
                elif op=='attach':await (await registry.resolveByPath(str(root/action['path']))).attachSession(action['id'])
                elif op=='detach':await (await registry.resolveByPath(str(root/action['path']))).detachSession(action['id'])
                elif op=='relative':
                    try:await registry.create(action['path'])
                    except TypeError as error:results.append(dict(error=str(error)));continue
                elif op!='view':raise ValueError(op)
                results.append(snapshot())
            return dict(results=results)
        finally:
            for ctx in reversed(contexts):await ctx.fiber.dispose()


def execute(test):return json.loads(json.dumps(asyncio.run(run(test))))
