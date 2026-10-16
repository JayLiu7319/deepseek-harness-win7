"""rc.3 read-only workspace previews and instrumented filesystem observations."""
import asyncio
import base64
import math
import ntpath
import posixpath
import re
from collections import deque
from urllib.parse import unquote, urlsplit

from dsh.typert.remote import Remote, RemoteError, TypertRemoteService
from dsh.typert.stores import field

MAX_SAFE_INTEGER=9007199254740991
DEFAULTS=dict(maxBytes=2*1024*1024,maxFileBytes=32*1024*1024,maxLines=5000,maxEntries=2000)


def integer_at_least(value, minimum, name):
    if type(value) not in (int,float) or abs(value)>MAX_SAFE_INTEGER or not math.isfinite(value) or value!=int(value) or value<minimum:
        raise RemoteError('gateway/bad-request','{} must be a safe integer of at least {}'.format(name,minimum),{})
    return int(value)


def byte_length(text):
    return len(text.encode('utf-16-le','surrogatepass').decode('utf-16-le','replace').encode('utf-8'))


async def cut_page(chunks,offset,limit,max_bytes,path):
    last=offset+limit-1
    lines,current,bytes_used,line_number=[],'',0,1
    def admit(size):
        nonlocal bytes_used
        bytes_used+=size
        if bytes_used>max_bytes:
            raise RemoteError('workspace-file/too-large','lines {}-{} of "{}" exceed the {} byte cap'.format(offset,last,path,max_bytes),dict(path=path,limit=max_bytes))
    def complete():
        nonlocal current
        if lines:admit(1)
        lines.append(current);current=''
    iterator=chunks.__aiter__()
    try:
        async for chunk in iterator:
            position=0
            while position<len(chunk):
                if line_number>last:return dict(text='\n'.join(lines),lines=len(lines),eof=False)
                newline=chunk.find('\n',position)
                segment=chunk[position:] if newline==-1 else chunk[position:newline]
                if line_number>=offset:
                    admit(byte_length(segment));current+=segment
                if newline==-1:break
                if line_number>=offset:complete()
                line_number+=1;position=newline+1
        if current:complete()
        return dict(text='\n'.join(lines),lines=len(lines),eof=True)
    finally:
        close=getattr(iterator,'aclose',None)
        if close is not None:await close()


class ChangeFollower:
    def __init__(self):
        self.queue,self.wake,self.closed=deque(),asyncio.Event(),False

    def push(self,observation):
        self.queue.append(observation);self.wake.set()

    def close(self):
        self.closed=True;self.wake.set()

    async def read(self,signal):
        release=signal.add_listener('abort',lambda *_:self.close())
        try:
            while not self.closed:
                if self.queue:
                    yield self.queue.popleft();continue
                self.wake.clear()
                await self.wake.wait()
        finally:release()


class WorkspaceChangeFeed:
    def __init__(self,ctx):
        self.ctx,self.followers=ctx,set()
        ctx.on('fs/observed',self.observed)
        ctx.effect(lambda:self.close,'workspace-files.changes')

    def observed(self,target,observation,*_):
        for follower in self.followers:follower.push((target,observation))

    def close(self):
        for follower in self.followers:follower.close()
        self.followers.clear()

    async def follow(self,workspace_root,signal):
        signal.throwIfAborted()
        follower=ChangeFollower();self.followers.add(follower)
        try:
            try:root=await self.ctx.get('fs').resolve(workspace_root,dict(signal=signal))
            except Exception:
                if signal.aborted:return
                raise
            if root is None or signal.aborted or follower.closed:return
            yield dict(kind='ready')
            reader=follower.read(signal)
            try:
                async for target,observation in reader:
                    fs=self.ctx.get('fs')
                    if not fs.contains(root,target):continue
                    change=dict(absolutePath=fs.processPath(target))
                    change.update(dict(version=field(observation,'version')) if field(observation,'kind')=='present' else dict(absent=True))
                    yield dict(kind='change',change=change)
            finally:await reader.aclose()
        finally:
            self.followers.discard(follower);follower.close()


class CurrentWorkspaceFiles(TypertRemoteService):
    inject=['fs','sandboxPolicy','sessions','typert']

    def __init__(self,ctx,config=None):
        super().__init__(ctx,'workspaceFiles')
        self.caps=dict(DEFAULTS,**(config or {}));self.feed=WorkspaceChangeFeed(ctx)
        def lookup(scope):
            async def resolve(sid):
                session=scope.get('sessions').get(sid)
                live=session.header if session is not None else None
                persistence=scope.get('sessionPersistence')
                stored=await persistence.stat(sid) if live is None and persistence is not None else None
                header=live if live is not None else field(stored,'header') if stored is not None else None
                if header is None:return None
                cwd=field(header,'cwd')
                return dict(sessionId=sid,workspaceRoot=cwd if cwd is not None else field(scope.get('sandboxPolicy'),'workspaceRoot'))
            scope.get('typert').lookups.register('workspaceFileScope',dict(parameter='workspaceFileScope',wire='workspaceFileScopeId',
                hostTypeSymbol='@deepseek-ai/dsh-api-workspace-files#WorkspaceFileScope',wireTypeSymbol='@deepseek-ai/dsh-session/types#SessionId',resolve=resolve))
        ctx.inject(['sessions','typert'],lookup)

    def resolve_page(self,range):
        offset=integer_at_least(range['offset'],1,'offset') if 'offset' in range else 1
        limit=integer_at_least(range['limit'],1,'limit') if 'limit' in range else self.caps['maxLines']
        if limit>self.caps['maxLines']:raise RemoteError('gateway/bad-request','limit must be at most {}'.format(self.caps['maxLines']),{})
        return offset,limit

    def resolve_window(self,range,path):
        offset=integer_at_least(range['offset'],0,'offset') if 'offset' in range else 0
        length=integer_at_least(range['length'],1,'length') if 'length' in range else self.caps['maxBytes']
        if offset+length>MAX_SAFE_INTEGER:raise RemoteError('gateway/bad-request','offset plus length must stay a safe integer',{})
        maximum=self.caps['maxBytes']
        if length>maximum:raise RemoteError('workspace-file/too-large','{} bytes of "{}" exceed the {} byte cap'.format(length,path,maximum),dict(path=path,limit=maximum))
        return offset,length

    async def inspect(self,scope,path,signal):
        if not path:raise RemoteError('gateway/bad-request','path is required',{})
        workspace_root=field(scope,'workspaceRoot');fs=self.ctx.get('fs')
        root=await fs.resolve(workspace_root,dict(signal=signal))
        entry=await fs.lstat(path,dict(cwd=workspace_root),signal)
        if entry is None:raise RemoteError('workspace-file/not-found','no entry at "{}"'.format(path),dict(path=path))
        return root,workspace_root,entry

    async def locate_file(self,scope,path,signal):
        _,workspace_root,entry=await self.inspect(scope,path,signal)
        def regular(info):
            kind=field(info,'type')
            if kind!='file':raise RemoteError('workspace-file/not-regular-file','"{}" is a {}'.format(path,kind),dict(path=path,kind=kind))
        regular(entry)
        fs=self.ctx.get('fs');target=await fs.resolve(path,dict(cwd=workspace_root,signal=signal));info=await fs.stat(target,signal)
        if info is None:raise RemoteError('workspace-file/not-found','no entry at "{}"'.format(path),dict(path=path))
        regular(info);return target,info

    def stat_of(self,target,info):
        value=dict(absolutePath=self.ctx.get('fs').processPath(target),version=field(info,'version'))
        if field(info,'size') is not None:value['bytes']=field(info,'size')
        return value

    @Remote
    async def read(self,workspaceFileScope,path,range,signal):
        offset,limit=self.resolve_page(range);target,info=await self.locate_file(workspaceFileScope,path,signal)
        try:page=await cut_page(await self.ctx.get('fs').streamText(target,signal),offset,limit,self.caps['maxBytes'],path)
        except Exception as error:
            if getattr(error,'code',None)=='FS_NOT_TEXT':raise RemoteError('workspace-file/not-text','"{}" is not UTF-8 text'.format(path),dict(path=path),cause=error) from None
            raise
        if '\0' in page['text']:raise RemoteError('workspace-file/not-text','"{}" contains NUL bytes'.format(path),dict(path=path))
        return dict(self.stat_of(target,info),offset=offset,**page)

    @Remote
    async def readBytes(self,workspaceFileScope,path,range,signal):
        offset,length=self.resolve_window(range,path);target,info=await self.locate_file(workspaceFileScope,path,signal)
        data=await self.ctx.get('fs').readByteRange(target,dict(offset=offset,length=length),signal)
        size=field(info,'size');eof=len(data)<length if size is None else offset+len(data)>=size
        return dict(self.stat_of(target,info),offset=offset,data=base64.b64encode(data).decode('ascii'),eof=eof)

    @Remote
    async def readAll(self,workspaceFileScope,path,signal):
        target,info=await self.locate_file(workspaceFileScope,path,signal);limit=self.caps['maxFileBytes']
        def too_large():raise RemoteError('workspace-file/too-large','"{}" exceeds the {} byte full-file cap'.format(path,limit),dict(path=path,limit=limit))
        if field(info,'size') is not None and field(info,'size')>limit:too_large()
        data=await self.ctx.get('fs').readByteRange(target,dict(offset=0,length=limit+1),signal)
        if len(data)>limit:too_large()
        return dict(self.stat_of(target,info),offset=0,data=base64.b64encode(data).decode('ascii'),eof=True)

    @Remote
    async def readRelated(self,workspaceFileScope,path,relativePath,signal):
        relative=relativePath.replace('\\','/')
        if not relative or relative.startswith('/') or re.match(r'^[a-zA-ZſK][a-zA-ZſK0-9+.-]*:',relative) or '\0' in relative:
            raise RemoteError('gateway/bad-request','relativePath must be a relative filesystem path',{})
        target,_=await self.locate_file(workspaceFileScope,path,signal)
        absolute=self.ctx.get('fs').processPath(target);paths=posixpath if absolute.startswith('/') else ntpath
        related=paths.normpath(paths.join(paths.dirname(absolute),relative))
        return await self.readAll(workspaceFileScope,related,signal)

    @Remote
    async def stat(self,workspaceFileScope,path,signal):
        return self.stat_of(*(await self.locate_file(workspaceFileScope,path,signal)))

    @Remote
    async def list(self,workspaceFileScope,path,signal):
        root,workspace_root,entry=await self.inspect(workspaceFileScope,path,signal)
        kind=field(entry,'type')
        if kind!='directory':raise RemoteError('workspace-file/not-directory','"{}" is a {}'.format(path,kind),dict(path=path,kind=kind))
        fs=self.ctx.get('fs');target=await fs.resolve(path,dict(cwd=workspace_root,signal=signal))
        if not fs.contains(root,target):raise RemoteError('workspace-file/outside-workspace','"{}" is outside the workspace'.format(path),dict(path=path))
        children=await fs.listDir(target,signal)
        root_path=urlsplit(fs.fileUrl(root)).path.rstrip('/');target_path=urlsplit(fs.fileUrl(target)).path
        workspace_path='' if target_path==root_path else '/'.join(unquote(segment,errors='strict') for segment in target_path[len(root_path)+1:].split('/'))
        entries=[]
        for child in children[:self.caps['maxEntries']]:
            value=dict(name=field(child,'name'),type=field(child,'type'))
            if field(child,'size') is not None:value['size']=field(child,'size')
            entries.append(value)
        return dict(path=workspace_path,entries=entries,truncated=len(children)>self.caps['maxEntries'])

    @Remote(dict(mode='stream'))
    def changes(self,workspaceFileScope,signal):
        return self.feed.follow(field(workspaceFileScope,'workspaceRoot'),signal)
