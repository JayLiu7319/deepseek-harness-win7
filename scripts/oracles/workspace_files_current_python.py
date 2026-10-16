"""Current workspace preview Remote over an opaque controlled filesystem seam."""
import asyncio
import base64
import json
import ntpath
import posixpath
from types import SimpleNamespace
from urllib.parse import quote

from dsh.api.workspace_files_current import CurrentWorkspaceFiles,DEFAULTS
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.fs.fs_local import FsError
from dsh.typert.current import CurrentTypertRegistry
from dsh.typert.stores import field


async def run(case):
    ctx,controller,calls,results,streams=Context(),AbortController(),[],[],{}
    root=case.get('root','/project');paths=posixpath if root.startswith('/') else ntpath
    closed=[]
    def absolute(path,cwd=None):return paths.normpath(path if paths.isabs(path) else paths.join(cwd or root,path))
    def target(path):return SimpleNamespace(key=path,displayPath=path)
    def contains(parent,child):
        relative=paths.relpath(child.key,parent.key)
        return relative=='.' or relative!='..' and not relative.startswith('..'+paths.sep) and not paths.isabs(relative)
    def info(kind='file'):
        return dict(type=kind,version='v1',**({} if case.get('unknownSize') else dict(size=case.get('size',len(base64.b64decode(case.get('data','Ynl0ZXM=')))))))
    async def resolve(path,options=None):
        options=options or {};calls.append(dict(op='resolve',path=path,**(dict(cwd=options['cwd']) if 'cwd'in options else {}),signal=options.get('signal') is controller.signal))
        if path==root:
            for observation in case.get('openingObservations',[]):ctx.emit('fs/observed',target(absolute(observation['path'])),observation['observation'])
        if case.get('resolveError'):raise FsError('resolve refused',case['resolveError'])
        if options.get('signal') is not None:options['signal'].throwIfAborted()
        return target(absolute(path,options.get('cwd')))
    async def lstat(path,options,signal):
        calls.append(dict(op='lstat',path=path,cwd=options['cwd'],signal=signal is controller.signal))
        return None if case.get('missing') else info(case.get('entryKind','file'))
    async def stat(item,signal):
        calls.append(dict(op='stat',target=item.key,signal=signal is controller.signal))
        return None if case.get('vanished') else info(case.get('statKind','file'))
    async def stream(item,signal):
        calls.append(dict(op='stream',target=item.key,signal=signal is controller.signal))
        async def chunks():
            try:
                for text in case.get('chunks',['one\ntwo\nthree']):
                    calls.append(dict(op='chunk',text=text));yield text
                if case.get('textError'):raise FsError('backend rejected text',case['textError'])
            finally:closed.append(True)
        return chunks()
    async def byte_range(item,window,signal):
        calls.append(dict(op='bytes',target=item.key,range=window,signal=signal is controller.signal))
        data=base64.b64decode(case.get('data','Ynl0ZXM='));return data[window['offset']:window['offset']+window['length']]
    async def listing(item,signal):
        calls.append(dict(op='list',target=item.key,signal=signal is controller.signal))
        return [dict(row,target=target('/opaque/'+row['name'])) for row in case.get('entries',[])]
    async def persisted(sid):
        calls.append(dict(op='persisted-stat',sessionId=sid))
        return None if case.get('noHeader') else dict(header=case.get('header',dict(cwd=root)))
    async def next_frame(name):
        try:return dict(done=False,value=await asyncio.wait_for(streams[name].__anext__(),2))
        except StopAsyncIteration:return dict(done=True)
    try:
        await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(CurrentTypertRegistry)
        ctx.set_service('fs',SimpleNamespace(resolve=resolve,lstat=lstat,stat=stat,streamText=stream,readByteRange=byte_range,listDir=listing,contains=contains,processPath=lambda item:item.key,fileUrl=lambda item:'file:///'+quote(item.key.lstrip('/').replace('\\','/'),safe='/:' )))
        ctx.set_service('sandboxPolicy',SimpleNamespace(workspaceRoot='/fallback'))
        ctx.set_service('sessionPersistence',SimpleNamespace(stat=persisted))
        if case.get('liveHeader') is not None:ctx.get('sessions').create('one',dict(meta=case['liveHeader']))
        fiber=await ctx.plugin(CurrentWorkspaceFiles,case.get('config',{}));api=ctx.get('workspaceFiles')
        scope=dict(sessionId='one',workspaceRoot=root)
        for action in case['actions']:
            try:
                op=action['op']
                if op=='lookup':value=await field(ctx.get('typert').lookups.get('workspaceFileScope'),'resolve')('one')
                elif op=='change':
                    streams[action.get('name','feed')]=api.changes(scope,controller.signal);value=await next_frame(action.get('name','feed'))
                elif op=='next':value=await next_frame(action.get('name','feed'))
                elif op=='observed':
                    ctx.emit('fs/observed',target(absolute(action['path'])),action['observation']);value=True
                elif op=='abort':controller.abort(RuntimeError('caller cancelled'));value=True
                elif op=='close':await fiber.dispose();value=dict(lookup=ctx.get('typert').lookups.has('workspaceFileScope'))
                else:
                    args=[scope,action.get('path','file.txt')]
                    if op in ('read','readBytes'):args.append(action.get('range',{}))
                    if op=='readRelated':args.append(action['relative'])
                    value=await getattr(api,op)(*args,controller.signal)
                results.append(dict(outcome='value',value=value))
            except Exception as error:
                results.append(dict(outcome='error',error=dict(message=str(error),**(dict(code=error.code) if hasattr(error,'code') else {}),**(dict(details=error.details) if hasattr(error,'details') else {}))))
        return dict(results=results,calls=calls,closed=len(closed))
    finally:
        controller.abort()
        for iterator in streams.values():await iterator.aclose()
        await ctx.fiber.dispose()


def execute(case):return json.loads(json.dumps(asyncio.run(run(case))))
