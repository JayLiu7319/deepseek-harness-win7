"""Finite query journeys, executed against actual services on both sides."""
import json
from pathlib import Path


def generate():
    cases=[]
    def event(kind,seq,data,**opts):return dict(type=kind,seq=seq,time=seq+1,data=data,**opts)
    def user(seq,text):return event('user/message',seq,dict(id='u'+str(seq),role='user',content=[dict(type='text',text=text)],source=dict(kind='user')),surfaceOp='append')
    def system(seq,text,**opts):return event('system/message',seq,dict(turn=1,step=1,message=dict(id='s'+str(seq),role='system',source=dict(kind='plugin',plugin='test'),content=[dict(type='text',text=text)])),surfaceOp=opts.pop('surfaceOp','append'),**opts)
    header=dict(version=3,id='cold',createdAt=1,isSeeded=False)
    base=[system(0,'system only'),user(1,'needle one'),user(2,'needle needle two')]
    def call(method,*args,**opts):return dict(method=method,args=list(args),**opts)
    def case(name,actions,events=base,**opts):
        cases.append(dict(case=name,kind='query-current',stored=[dict(header=header,events=events)],actions=actions,**opts))
    for name,args in [('listSessions',[]),('readSession',['cold']),('readSurface',['cold']),('listEvents',['cold']),
                      ('readEvent',[dict(sessionId='cold',seq=0,after=2)]),('traceEvent',[dict(sessionId='cold',seq=1)]),
                      ('filterEvents',['cold',[dict(kind='surface',values=['current'])]]),
                      ('filterSessions',[[dict(kind='availability',values=['persisted'])]]),
                      ('traceSession',['cold']),('readTitleSnapshot',['cold']),('readTitleSnapshots',[['cold','missing','cold']]),
                      ('searchSessions',[dict(query='needle')]),('searchEvents',[dict(sessionId='cold',query='needle')])]:
        case('exact/'+name,[call(name,*args)])
    replaced=base+[system(3,'changed system',surfaceOp=dict(op='replace',startSeq=0,endSeq=0),sourceEventSeqs=[0])]
    case('surface/system-replacement',[call('readSurface','cold'),call('listEvents','cold'),call('traceEvent',dict(sessionId='cold',seq=0)),call('searchEvents',dict(sessionId='cold',query='needle'))],replaced)
    case('empty/all',[call('readSession','cold'),call('readSurface','cold'),call('observe','cold'),call('searchSessions',dict(query='needle'))],[])
    case('interrupted/balanced',[call('observe','cold'),call('readSession','cold'),call('searchEvents',dict(sessionId='cold',query='interrupted'))],
         [event('turn/start',0,dict(turn=1)),user(1,'needle')])
    case('observe/revision-and-retention',[call('observe','cold'),call('retain',lease='old'),
         call('appendStored',id='cold',events=[user(3,'latest needle')]),call('observe','cold',lease='new'),
         call('view',lease='old'),call('release',lease='old'),call('retain',lease='invalid',**{'from':'old'})])
    case('live/shadows-cold',[call('live',id='cold',meta=dict(createdAt=1),events=[user(0,'needle live')]),
         call('listSessions'),call('searchEvents',dict(sessionId='cold',query='needle')),call('readSession','cold'),call('observe','cold')])
    case('live/header-conflict',[call('live',id='cold',meta=dict(createdAt=2)),call('listSessions'),call('searchSessions',dict(query='needle'))])
    case('search/refresh',[call('searchSessions',dict(query='needle')),call('appendStored',id='cold',events=[user(3,'needle latest')]),
         call('searchSessions',dict(query='needle')),call('searchEvents',dict(sessionId='cold',query='needle',limit=1))])
    case('search/pagination-token',[call('searchEvents',dict(sessionId='cold',query='needle',limit=1))])
    for method,args in [('readSession',['missing']),('observe',['missing']),('searchEvents',[dict(sessionId='missing',query='needle')]),
                        ('readEvent',[dict(sessionId='cold',seq=9)]),('traceEvent',[dict(sessionId='cold',seq=-1)]),
                        ('readEvent',[dict(sessionId='cold',seq=1,before=51)])]:
        case('refusal/'+method+'/'+str(len(cases)),[call(method,*args)])
    case('search/disabled-exact-available',[call('searchSessions',dict(query='needle')),call('readSession','cold'),call('observe','cold')],config=dict(openAt='never'))
    history=json.loads(Path(__file__).with_name('session_generation_cases.json').read_text(encoding='utf8'))
    for version in [0,1,2]:
        raw=next(c['raw'] for c in history if c['case']=='generation/none/v%s/publish'%version)
        cases.append(dict(case='history/v'+str(version),kind='query-current',files=[dict(path='_no-cwd/generation/session'+('.v'+str(version) if version else '')+'.jsonl',raw=raw)],
            actions=[call('listSessions'),call('observe','generation'),call('readSession','generation'),call('searchSessions',dict(query='hello'))]))
    return cases


if __name__=='__main__':
    cases=generate()
    Path(__file__).with_name('session_query_current_cases.json').write_text(json.dumps(cases,separators=(',',':'))+'\n',encoding='utf8')
    print(len(cases))
