"""Real native backend filesystem journeys; opaque revision equality is observed."""
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistence
from dsh.session.jsonl_zstd import compress_frame
from scripts.oracles.session_storage_current_python import error_record


async def run_case(test,decode):
    with tempfile.TemporaryDirectory(prefix='dsh-backend-pair-') as root:
        instances,handles,results,revisions=[],{},[],{}
        async def outcome(run):
            try:
                value=run()
                if hasattr(value,'__await__'):value=await value
                return dict(outcome='value',value=value)
            except Exception as error:return dict(outcome='error',**error_record(error))
        def mount():instances.append(CurrentJsonlSessionPersistence(root,test['compression']))
        def encode(raw):return compress_frame(raw.encode('utf8')) if test['compression']=='zstd' else raw.encode('utf8')
        def write(file,append=False):
            path=Path(root)/file['path'];path.parent.mkdir(parents=True,exist_ok=True)
            if 'frames' in file:data=b''.join(encode(raw) for raw in file['frames'])
            elif test['compression']=='zstd' and not file.get('literal'):
                i=file['raw'].index('\n')+1;data=encode(file['raw'][:i])+(encode(file['raw'][i:]) if file['raw'][i:] else b'')
            else:data=file['raw'].encode('utf8')
            if 'truncate' in file:data=data[:-file['truncate']]
            with path.open('ab' if append else 'wb') as stream:stream.write(data)
        def snapshot(value):
            if isinstance(value,list):return [snapshot(v) for v in value]
            if isinstance(value,dict):
                record={}
                for key,child in value.items():
                    if key=='revision':
                        if child not in revisions:revisions[child]='revision:%s'%(len(revisions)+1)
                        record[key]=revisions[child]
                    else:record[key]=snapshot(child)
                return record
            return value
        try:
            for file in test.get('files',[]):write(file)
            mount()
            for action in test['actions']:
                async def run():
                    p=instances[action.get('backend',0)];method=action['method']
                    if method=='other':mount();return
                    if method=='physical':return write(action['file'],action.get('append',False))
                    if method=='dispose':return await p.close()
                    if method in ('create','open'):
                        h=await getattr(p,method)(*decode(action['args']));handles[action.get('handle','h')]=h
                        return dict(id=h.id,header=h.header,access=h.access)
                    if method in ('stat','list','flush'):return await getattr(p,method)(*decode(action.get('args',[])))
                    return await getattr(handles[action.get('handle','h')],method)(*decode(action.get('args',[])))
                results.append(snapshot(await outcome(run)))
            teardown=[await outcome(p.close) for p in instances]
            files=[]
            for parent,_,names in os.walk(root):
                for name in names:
                    path=Path(parent)/name;data=path.read_bytes();files.append(dict(path=path.relative_to(root).as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
            files.sort(key=lambda file:file['path'])
            print(json.dumps(dict(case=test['case'],rawRevisions=list(revisions.items()))))
            def normalize(v):
                if isinstance(v,str):return v.replace(root.replace('\\','\\\\'),'<root>').replace(root,'<root>')
                if isinstance(v,list):return [normalize(x) for x in v]
                if isinstance(v,dict):return {k:normalize(x) for k,x in v.items()}
                return v
            return normalize(dict(results=results,teardown=teardown,files=files))
        finally:
            for p in instances:
                try:await p.close()
                except Exception:pass


def execute(test,decode):return asyncio.run(run_case(test,decode))
