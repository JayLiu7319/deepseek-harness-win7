"""Explicit persistence admission, ownership, read and failure/retry scenarios."""
import copy
import json
from pathlib import Path


def generate():
    cases=[]
    def add(name,**value):cases.append(dict(case=name,**value))
    h=dict(version=3,id='paired-session',createdAt=1,isSeeded=False)
    def event(seq=0):return dict(type='turn/start',seq=seq,time=1,data=dict(turn=1))
    def call(method,*args):return dict(method=method,args=list(args))
    def helper(name,method,*args):add(name,kind='storage-contract',method=method,args=list(args))
    for version in [0,1,2,3,4,45,-1,True,3.0]:
        for location in [None,dict(kind='jsonl',path='/raw/log.v3.jsonl')]:
            helper('version-%s-%s'%(version,bool(location)),'assertVersion',dict(h,version=version),*([location] if location else []))
    for identity in ['paired-session','different','',None]:helper('identity-%s'%identity,'assertStoredId',identity,h)
    for value in [0,1,1.0,9007199254740991,-1,0.5,9007199254740992,True,None,{'$scalar':'-0'},{'$scalar':'Infinity'},{'$scalar':'NaN'},{'$scalar':'undefined'}]:
        helper('metadata-%s'%str(value),'materializeCreateHeader',dict(h,createdAt=value))
    user=dict(type='user/message',seq=0,time=1,surfaceOp='append',data=dict(id='u',role='user',content=[dict(type='text',text='hi')],source=dict(kind='user')))
    events=[[],[event()],[user],[dict(event(),type='foreign/required')],[dict(event(),type='foreign/info',ignorable=True)],
            [dict(type='request/header',seq=0,time=1,data=dict(header=dict(config=dict(provider='mock',model='m')),reason='fallback'))],
            [dict(type='request/header',seq=0,time=1,data=dict(header=dict(config=dict(provider='mock',model='m')),reason='initial'))]]
    for key in ['id','role','content','source']:
        changed=copy.deepcopy(user);changed['data'].pop(key);events.append([changed])
    for key,value in [('surfaceOp','replace'),('surfaceSources',[0]),('surfaceOp',None)]:
        events.append([dict(user,**{key:value})])
    # Unknown required vocabulary must win before adoption of an earlier corrupt record.
    events.append([dict(user,data={}),dict(event(1),type='future')])
    for index,batch in enumerate(events):
        for location in [None,dict(kind='jsonl',path='/raw/log.v3.jsonl')]:
            helper('stored-%s-%s'%(index,bool(location)),'validateStoredEvents',h,batch,*([location] if location else []))
    for index,value in enumerate([None,True,{'$scalar':'undefined'},{'$scalar':'Infinity'},{'$scalar':'NaN'},{'$scalar':'-0'},'text',[],{}]):
        helper('append-data-%s'%index,'materializeAppendBatch',[dict(event(),data=dict(turn=1,extra=value))])
    for cursor in [0,1,4]:
        for seqs in [[],[0],[1],[4],[0,1],[0,2],[4,5],[4,6],[True],[0.0,1.0]]:
            helper('contiguous-%s-%s'%(cursor,str(seqs)),'assertContiguous','paired-session',[event(seq) for seq in seqs],cursor)
    def scenario(name,actions,**options):add(name,kind='storage-handle',actions=actions,**options)
    scenario('empty-close',[])
    scenario('explicit-empty-flush',[call('flush'),call('read')])
    scenario('append-snapshot',[dict(call('append',[event()]),mutate=True),call('read'),call('flush')])
    scenario('append-close',[dict(method='append-close',events=[event()]),call('read',-1),call('append',[]),call('flush'),call('close')])
    scenario('claim-create',[call('claim'),call('create'),call('flush'),call('close'),call('claim'),call('create')])
    for access in ['read','write']:
        for name,kwargs in [('pending',{}),('missing',dict(created=False)),('current',dict(path='/current',stored=dict(eventState='shared-frozen',events=[event()]))),('primed',dict(state=dict(cursor=1,materialized=True,inheritedEventCount=0,primed=dict(eventState='detached',events=[event()]))))]:
            scenario('read-%s-%s'%(access,name),[call('read'),call('read',0,0),call('read',1),call('append',[]),call('flush'),call('close'),call('read',-1)],access=access,**kwargs)
        for offset in [-1,True,0.5,9007199254740992,{'$scalar':'-0'},1.0]:
            scenario('offset-%s-%s'%(access,str(offset)),[call('read',offset)],access=access)
    scenario('monotonic-prefix',[call('read',1,0),dict(method='stored',value=dict(eventState='detached',events=[])),call('read')],path='/current',stored=dict(eventState='shared-frozen',events=[event()]))
    scenario('primed-read-promotes',[call('read'),dict(method='stored',path='/current',value=dict(eventState='shared-frozen',events=[event(),event(1)])),call('read')],access='read',state=dict(cursor=1,materialized=True,inheritedEventCount=0,primed=dict(eventState='detached',events=[event()])))
    scenario('primed-write-keeps-prefix',[call('read'),dict(method='stored',path='/current',value=dict(eventState='shared-frozen',events=[])),call('read')],state=dict(cursor=1,materialized=True,inheritedEventCount=0,primed=dict(eventState='detached',events=[event()])))
    for method in ['acquireWriteLease','persistBatch','persistHeader','truncateTornTail','release']:
        state=dict(cursor=0,materialized=False,inheritedEventCount=0)
        if method=='truncateTornTail':state['tornTruncateTo']=33
        scenario('retry-%s'%method,[call('flush') if method=='persistHeader' else call('append',[event()]),call('append',[event()]),call('close'),call('close')],state=state,fail={method:[1]})
    for failure in [{},{'persistBatch':[1]},{'persistBatch':[1,2]},{'acquireWriteLease':[1]},{'persistBatch':[1],'release':[1]}]:
        scenario('live-retry-%s'%str(failure),[dict(method='live',event=event()),call('drainLive'),call('drainLive'),dict(method='live',event=event(1)),call('flushAll'),call('close')],fail=failure)
    scenario('close-double-failure',[dict(method='live',event=event()),call('close'),call('close')],fail={'persistBatch':[1],'release':[1]},lease=True)
    for failure in [{},{'truncateTornTail':[1]},{'persistBatch':[1]},{'persistBatch':[2]}]:
        scenario('recovered-tail-%s'%str(failure),[call('append',[event(1)]),call('append',[event(1)]),call('read')],state=dict(cursor=1,materialized=True,inheritedEventCount=0,tornTruncateTo=23,recoveredTail=[event()],primed=dict(eventState='shared-frozen',events=[event()])),fail=failure)
    return cases


if __name__=='__main__':
    path=Path(__file__).with_name('session_storage_cases.json')
    cases=generate();path.write_text(json.dumps(cases,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8');print(len(cases))
