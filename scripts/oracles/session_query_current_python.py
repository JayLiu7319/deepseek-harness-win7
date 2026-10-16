"""Replay actual rc.3 query service journeys against native JSONL and SQLite."""
import asyncio
import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin
from dsh.session.query_current import CurrentSqliteSessionQueryPlugin


async def run(test,decode):
    root=Context();leases={};results=[];revisions={}
    def normalize(value,key=''):
        if isinstance(value,BaseException):
            result=dict(name=getattr(value,'name','TypeError' if isinstance(value,TypeError) else 'Error'),message=getattr(value,'message',str(value)))
            if getattr(value,'code',None):result['code']=value.code
            if getattr(value,'cause',None) is not None:result['cause']=normalize(value.cause)
            return result
        if key=='nextCursor':
            cursor=json.loads(base64.urlsafe_b64decode(value+'='*(-len(value)%4)));cursor['instance']='<instance>';return cursor
        if key=='revision':
            if value not in revisions:revisions[value]='revision:'+str(len(revisions)+1)
            return revisions[value]
        if hasattr(value,'to_dict'):value=value.to_dict()
        if isinstance(value,dict):return {k:normalize(v,k) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [normalize(v) for v in value]
        return value
    def view(lease):
        result={key:getattr(lease,key) for key in ('source','header','inheritedEventCount','events','cursor')}
        if 'revision' in lease._view:result['revision']=lease.revision
        return result
    with tempfile.TemporaryDirectory(prefix='dsh-query-pair-') as folder:
        try:
            await root.plugin(CurrentSessionPlugin)
            await root.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=folder,compression='none'))
            p=root.get('sessionPersistence')
            for entry in test.get('stored',[]):
                h=await p.create(entry['header'],entry.get('options'))
                try:await h.append(entry['events']);await h.flush()
                finally:await h.close()
            for file in test.get('files',[]):
                path=Path(folder)/file['path'];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(file['raw'],encoding='utf8')
            config=dict(path=':memory:',openAt='first-search');config.update(test.get('config',{}))
            await root.plugin(CurrentSqliteSessionQueryPlugin,config)
            q=root.get('sessionQuery')
            for action in test['actions']:
                try:
                    value=None;args=decode(action.get('args',[]));method=action['method']
                    if method=='live':
                        session=root.get('sessions').create(action['id'],dict(meta=action.get('meta',{})))
                        for event in action.get('events',[]):session.append(event['type'],event['data'],opts={key:event[key] for key in ('surfaceOp','sourceEventSeqs') if key in event})
                    elif method=='appendStored':
                        h=await p.open(action['id'],'write')
                        try:await h.append(action['events'])
                        finally:await h.close()
                    elif method=='observe':
                        lease=await q.observeSession(*args);leases[action.get('lease','o')]=lease;value=view(lease)
                    elif method=='retain':
                        lease=leases[action.get('from','o')].retain();leases[action['lease']]=lease;value=view(lease)
                    elif method=='release':leases[action.get('lease','o')].dispose()
                    elif method=='view':value=view(leases[action.get('lease','o')])
                    else:value=await getattr(q,method)(*args)
                    results.append(dict(outcome='value',value=normalize(value)))
                except Exception as error:
                    result=dict(outcome='error',**normalize(error))
                    if getattr(error,'code',None):result['code']=error.code
                    cause=getattr(error,'cause',None)
                    if cause is not None:result['cause']=getattr(cause,'message',str(cause)) if isinstance(cause,BaseException) else cause
                    results.append(result)
            print(json.dumps(dict(case=test['case'],rawRevisions=list(revisions.items()))))
            return results
        finally:
            for lease in leases.values():lease.dispose()
            await root.fiber.dispose()


def execute(test,decode):
    with patch.object(CurrentSession,'_event_time',lambda self:1000):
        return asyncio.run(run(test,decode))
