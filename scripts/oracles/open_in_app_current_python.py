"""Frozen Source comparisons with actual private filesystem artifacts."""
import asyncio
import json
import tempfile
from pathlib import Path
from dsh.host import open_in_app_resolver_current as api


async def run(test):
    operation = test['operation']
    if operation == 'catalog':
        return api.CATALOG
    if operation == 'desktop':
        return api.parse_desktop_entry(test['text'])
    if operation == 'exec':
        return api.exec_command(test.get('text'))
    if operation == 'registry':
        return [[key, list(values.items())] for key, values in api.parse_registry_dump(test['text']).items()]
    if operation == 'versions':
        return api.newest_first(test['values'])
    facts = dict(home='HOME', env=test.get('env', {}), resolveExecutable=lambda _: None)
    if operation == 'expand':
        return api.expand_candidate(test['text'], facts)
    if operation == 'xdg':
        return api.xdg_data_directories(facts)
    if operation == 'launch':
        calls=[]
        async def launch(command,args,options):
            calls.append(dict(command=command,args=args,options=options))
            outcome=test['outcomes'][len(calls)-1]
            if outcome != 'launched':
                error=RuntimeError('launch rejected');error.code='ENOENT' if outcome=='missing' else 'EACCES';raise error
        async def resolve(_):return None
        outcome=await api.launch_resolved(test['resolved'],test['path'],123,dict(resolveExecutable=resolve,launch=launch))
        return dict(outcome=outcome,calls=calls)
    with tempfile.TemporaryDirectory(prefix='rc3-open-app-') as directory:
        root=Path(directory)
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
        for name in test.get('directories',[]):(root/name).mkdir(parents=True,exist_ok=True)
        for name,contents in test.get('files',{}).items():
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(expand(contents),encoding='utf-8')
        calls=[]
        async def resolve(name):calls.append(dict(resolve=name));return expand(test.get('executables',{}).get(name))
        async def command(name,args,signal):
            calls.append(dict(command=name,args=args))
            value=expand(test.get('commands',{}).get(args[1] if name=='reg.exe' else name))
            if value is None:raise RuntimeError('unavailable')
            return dict(stdout=value,stderr='')
        facts=expand(dict(platform=test.get('platform','win32'),ssh=test.get('ssh',False),env=test.get('env',{}),home='$ROOT/home',applicationRoots=['$ROOT/apps']))
        facts.update(resolveExecutable=resolve,run=command)
        if operation=='registry-view':
            result=await api.read_windows_registry_view(1000,api.resolve_internals(facts))
            result['appPaths']=list(result['appPaths'].items())
        elif operation=='resolve':result=await api.resolve_launch(expand(test['app']),1000,facts)
        elif operation=='all':result=list((await api.resolve_open_in_app_apps(1000,facts)).items())
        else:raise ValueError(operation)
        return normalize(dict(result=result,calls=calls))


def execute(test):return json.loads(json.dumps(asyncio.run(run(test))))
