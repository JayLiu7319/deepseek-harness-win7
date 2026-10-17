"""Original HTTP callbacks/icon extraction over real owned files and host seams."""
import asyncio
import base64
import json
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from dsh.cordis.context import Context
from dsh.cordis.environment import LaunchEnvironmentSnapshot
from dsh.host.open_in_app_current import CurrentOpenInApp
from dsh.host.open_in_app_icons_current import extract_app_icon, EXTRACT_ICON_PS1


async def run(test):
    with tempfile.TemporaryDirectory(prefix='rc3-open-app-host-') as directory:
        root=Path(directory);ctx=Context();routes={};probes=Counter();launches=[];commands=[];temp_paths=[]
        def expand(value):
            if isinstance(value,str):return value.replace('$ROOT',str(root))
            if isinstance(value,list):return [expand(item) for item in value]
            if isinstance(value,dict):return {key:expand(item) for key,item in value.items()}
            return value
        def normalize(value):
            if isinstance(value,str):return value.replace(str(root),'$ROOT').replace('\\','/')
            if isinstance(value,(list,tuple)):return [normalize(item) for item in value]
            if isinstance(value,dict):return {key:normalize(item) for key,item in value.items()}
            return value
        for name in test.get('directories',['workspace','apps/Cursor.app/Contents/Resources']):(root/name).mkdir(parents=True,exist_ok=True)
        for name,content in test.get('files',{'apps/Cursor.app/Contents/Resources/AppIcon.icns':'icns'}).items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(expand(content),encoding='utf-8')
        async def resolve(name):
            probes[name]+=1
            path=expand(test.get('executables',{}).get(name))
            return None if test.get('resolveFromDisk') and (path is None or not Path(path).is_file()) else path
        async def launch(command,args,options):
            launches.append(dict(command=command,args=args,options=options))
            outcome=test.get('outcomes',['launched'])[min(len(launches)-1,len(test.get('outcomes',['launched']))-1)]
            if test.get('removeOnLaunch'):
                path=root/test['removeOnLaunch']
                if path.exists():path.unlink()
            if outcome!='launched':
                error=RuntimeError('failed');error.code='ENOENT' if outcome=='missing' else 'EACCES';raise error
        async def run_command(command,args,signal):
            if command in ('sips','powershell.exe'):
                target=Path(args[-1]);temp_paths.append(target.parent)
                if command=='powershell.exe':
                    script=Path(args[-3]);commands.append(dict(command=command,flags=args[:5],executable=args[-2],script=script.read_text(encoding='utf-8')))
                else:commands.append(dict(command=command,flags=args[:-1]))
                if test.get('commandFailure'):raise RuntimeError('extraction failure')
                if not test.get('noOutput'):target.write_bytes(b'\x89PNG\x00\xff')
                return dict(stdout='',stderr='')
            if command=='plutil':
                commands.append(dict(command=command,args=args))
                return dict(stdout=test.get('plist','{"CFBundleIconFile":"AppIcon"}'),stderr='')
            probes[command]+=1;raise RuntimeError('command unavailable')
        facts=expand(dict(platform=test.get('platform','darwin'),home='$ROOT/home',env=test.get('env',{}),applicationRoots=['$ROOT/apps']))
        facts.update(resolveExecutable=resolve,run=run_command,launch=launch)
        try:
            if test['operation']=='icon':
                result=await extract_app_icon(expand(test.get('app',dict(id='cursor',platforms={}))),expand(test.get('resolved',dict(launch=dict(kind='argv',command='open',args=[]),icon=dict(kind='app-bundle',path='$ROOT/apps/Cursor.app')))),1000,facts)
                return normalize(dict(icon=None if result is None else dict(contentType=result['contentType'],base64=base64.b64encode(result['bytes']).decode('ascii')),commands=commands,tempsRemoved=all(not path.exists() for path in temp_paths)))
            ctx.set_service('launchEnvironment',LaunchEnvironmentSnapshot(expand(test.get('layers',[]))))
            trust=[test.get('rejection')]
            ctx.set_service('connection',SimpleNamespace(requestRejection=lambda _:trust[0]))
            ctx.set_service('subprocess',SimpleNamespace(resolveExecutable=resolve))
            def register(kind,path,handler):routes[path]=handler;return lambda:routes.pop(path,None)
            ctx.set_service('webServer',SimpleNamespace(register=register))
            class Plugin(CurrentOpenInApp):catalog_internals=facts
            fiber=await ctx.plugin(Plugin,dict(probeTimeoutMs=1000,iconTimeoutMs=1000,launchWatchMs=123))
            responses=[]
            class Response:
                def __init__(self):self.status=200;self.headers={};self.body=b''
                def write_status(self,value):self.status=value
                def write_header(self,key,value):self.headers[key.lower()]=value
                def write_body(self,value):self.body+=value
                async def finish(self):pass
            for action in test.get('requests',[{}]):
                if 'rejection' in action:trust[0]=action['rejection']
                path=action.get('path','/open-in-app/apps');response=Response()
                body=expand(action.get('body',dict(app='cursor',path='$ROOT/workspace')))
                text=action.get('text',json.dumps(body,ensure_ascii=False,separators=(',',':')))
                if 'size' in action:text='x'*action['size']
                request=dict(method=action.get('method','GET' if path!='/open-in-app/open' else 'POST'),path=path,raw_url=path,headers=action.get('headers',{'content-type':'application/json'}),body=text.encode('utf-8'))
                if action.get('unreadable'):
                    class Broken:
                        async def read(self,n):raise OSError('body unavailable')
                    request.update(body_deferred=True,reader=Broken(),headers={'content-type':'application/json','content-length':'1'})
                handler=routes.get(path) or routes['/open-in-app/icon'] if path.startswith('/open-in-app/icon') else routes.get(path)
                await handler(request,response)
                data=response.body
                payload=json.loads(data.decode('utf-8')) if response.headers.get('content-type','').startswith('application/json') else dict(base64=base64.b64encode(data).decode('ascii'))
                responses.append(dict(status=response.status,headers=response.headers,body=payload))
            await fiber.dispose()
            return normalize(dict(responses=responses,probes=dict(sorted(probes.items())),launches=launches,commands=commands,withdrawn=not routes,tempsRemoved=all(not path.exists() for path in temp_paths)))
        finally:await ctx.fiber.dispose()


def execute(test):return asyncio.run(run(test))
