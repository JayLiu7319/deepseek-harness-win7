"""Drive native storage through the same external adapter as actual Source."""
import asyncio
import copy
from dsh.session import storage_contract
from dsh.session.jsonl_handle import JsonlSessionHandle, JsonlBackendTracker


def error_record(error):
    record = dict(name=getattr(error,'name','TypeError' if isinstance(error,TypeError) else 'Error'),message=str(error))
    if hasattr(error,'cause'):
        record['cause']=str(error.cause)
    if getattr(error,'location',None) is not None:
        record['location']=error.location
    if hasattr(error,'errors'):
        record['errors']=[error_record(e) for e in error.errors]
    return record


async def storage_case(test,decode):
    async def result(run):
        try:
            value=run()
            if hasattr(value,'__await__'):
                value=await value
            return dict(outcome='value',value=value)
        except Exception as error:
            return dict(outcome='error',**error_record(error))
    if test['kind']=='storage-contract':
        args=decode(test['args'])
        value=await result(lambda:getattr(storage_contract,test['method'])(*args))
        return dict(result=value,args=args)
    calls,counts,results,background=[],{},[],[]
    tracker=JsonlBackendTracker('paired')
    header=dict(version=3,id='paired-session',createdAt=1,isSeeded=False)
    state=copy.deepcopy(test.get('state',dict(cursor=0,materialized=False,inheritedEventCount=0)))
    current=dict(path=test.get('path'),stored=copy.deepcopy(test.get('stored',dict(eventState='shared-frozen',events=[]))))
    def invoke(name,*args):
        calls.append(dict(method=name,args=list(args)))
        counts[name]=counts.get(name,0)+1
        if counts[name] in test.get('fail',{}).get(name,[]):
            raise ValueError('%s failure %s'%(name,counts[name]))
    class Lease:
        async def release(self):invoke('release')
    lease=Lease()
    class Storage:
        async def persistBatch(self,h,events,materialized,cut):
            invoke('persistBatch',h,events,materialized,cut)
            current['stored']['events'].extend(events);current['path']='/current';tracker.materialized(h['id'])
        async def persistHeader(self,h,cut):
            invoke('persistHeader',h,cut);current['path']='/current';tracker.materialized(h['id'])
        async def truncateTornTail(self,h,offset):invoke('truncateTornTail',h,offset)
        async def resolveCurrentLog(self,session_id,signal=None):
            invoke('resolveCurrentLog',session_id);return current['path']
        async def readStoredLog(self,path,session_id,signal=None):
            invoke('readStoredLog',path,session_id);return current['stored']
        def hasPendingSession(self,session_id):return tracker.hasPending(session_id)
        async def acquireWriteLease(self,h):
            invoke('acquireWriteLease',h);return lease
        def releaseHandle(self,h,materialized):
            invoke('releaseHandle',h.id,materialized);tracker.release(h,materialized)
    if test.get('created',True):tracker.registerCreated(header,state['inheritedEventCount'])
    handle=tracker.adopt(JsonlSessionHandle(Storage(),header['id'],header,test.get('access','write'),state,lease if test.get('lease') else None))
    for action in test['actions']:
        async def run():
            method=action['method']
            if method=='live':return handle.enqueueLive(decode(action['event']),lambda error:background.append(error_record(error)))
            if method=='stored':
                current['stored']=decode(action['value']);current['path']=action.get('path',current['path']);return
            if method=='claim':return tracker.claimWrite(action.get('id',header['id']))
            if method=='create':return tracker.registerCreated(header,0)
            if method=='flushAll':return await tracker.flushAll()
            if method=='dispose':
                await asyncio.gather(*(h.close() for h in list(tracker.openHandles)));return
            if method=='append-close':
                pending=handle.append(decode(action['events']));closing=handle.close()
                return await asyncio.gather(result(lambda:pending),result(lambda:closing))
            args=decode(action.get('args',[]));pending=getattr(handle,method)(*args)
            if action.get('mutate'):args[0][0]['data']['turn']=99
            return await pending
        results.append(await result(run))
    close=await result(handle.close)
    return dict(results=results,calls=calls,state=state,stored=current['stored'],background=background,close=close,pending=list([key,value] for key,value in tracker.pendingEntries()),open=len(tracker.openHandles))


def execute(test,decode):
    import math
    from dsh.core.session.json import UNDEFINED
    def encode(value):
        if value is UNDEFINED:return {'$scalar':'undefined'}
        if isinstance(value,float):
            if not math.isfinite(value):return {'$scalar':'NaN' if math.isnan(value) else 'Infinity'}
            if value==0 and math.copysign(1,value)<0:return {'$scalar':'-0'}
        if isinstance(value,list):return [encode(v) for v in value]
        if isinstance(value,dict):return {k:encode(v) for k,v in value.items()}
        return value
    return encode(asyncio.run(storage_case(test,decode)))
