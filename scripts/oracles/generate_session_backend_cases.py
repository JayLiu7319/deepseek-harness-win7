"""Real filesystem service journeys across lazy/current/historical generations."""
import json
from pathlib import Path


def generate():
    cases=[]
    def call(method,*args,**kwargs):return dict(method=method,args=list(args),**kwargs)
    header=dict(version=3,id='generation',createdAt=1,isSeeded=False)
    events=[dict(type='turn/start',seq=0,time=1,data=dict(turn=1)),dict(type='turn/end',seq=1,time=2,data=dict(turn=1,reason=dict(kind='completed')))]
    history=json.loads(Path(__file__).with_name('session_generation_cases.json').read_text(encoding='utf8'))
    def raw(value):return json.dumps(value,separators=(',',':'),ensure_ascii=False)+'\n'
    for compression in ['none','zstd']:
        suffix='.jsonl'+('.zstd' if compression=='zstd' else '')
        def file(version,text,project='_no-cwd',**kwargs):return dict(path=project+'/generation/session'+('.v%s'%version if version else '')+suffix,raw=text,**kwargs)
        current=raw(dict(type='session',**header,delegationDepth=0))+''.join(raw(e) for e in events)
        def scenario(name,actions,files=None):cases.append(dict(case=compression+'/'+name,kind='storage-backend',compression=compression,actions=actions,files=files or []))
        scenario('lazy-forget',[call('create',header),call('stat','generation'),call('list'),call('other'),call('stat','generation',backend=1),call('open','generation','read',handle='r'),call('read',handle='r'),call('close'),call('stat','generation'),call('open','generation','write')])
        scenario('empty-flush-reopen',[call('create',header),call('flush'),call('stat','generation'),call('other'),call('open','generation','write',backend=1),call('close'),call('open','generation','write',backend=1),call('read'),call('close')])
        scenario('append-and-foreign-freshness',[call('create',header),call('append',[events[0]]),call('open','generation','read',handle='r'),call('read',handle='r'),call('stat','generation'),call('append',[events[1]]),call('read',handle='r'),call('stat','generation'),call('close'),call('other'),call('open','generation','write',backend=1),call('read')])
        scenario('new-materialization-race',[call('create',header),call('other'),call('create',header,backend=1,handle='foreign'),call('append',events),call('append',events,handle='foreign'),call('close'),call('append',events,handle='foreign'),call('stat','generation',backend=1)])
        scenario('current-cold',[call('list'),call('stat','generation'),call('open','generation','read'),call('read'),call('read',1,1),call('close'),call('open','generation','write'),call('read')],[file(3,current)])
        scenario('seeded-lazy',[call('create',dict(header,isSeeded=True),dict(inheritedEventCount=2)),call('append',events),call('close'),call('open','generation','read'),call('read'),call('stat','generation')])
        scenario('seeded-cut-required',[call('create',dict(header,isSeeded=True)),call('create',header,dict(inheritedEventCount=2))])
        for version in [0,1,2]:
            original=next(row['raw'] for row in history if row['version']==version and row['case']=='generation/none/v%s/publish'%version)
            scenario('historical-v%s-read'%version,[call('stat','generation'),call('list'),call('open','generation','read'),call('read'),call('close')],[file(version,original)])
            scenario('historical-v%s-publish'%version,[call('open','generation','read',handle='r'),call('read',handle='r'),call('open','generation','write'),call('read'),call('read',handle='r'),call('stat','generation'),call('close'),call('other'),call('open','generation','read',backend=1),call('read')],[file(version,original)])
        scenario('highest-canonical',[call('open','generation','read'),call('read'),call('stat','generation')],[file(0,raw(dict(type='session',version=0,id='generation',createdAt=1,delegationDepth=0))),file(3,current),dict(path='_no-cwd/generation/session.v03'+suffix,raw='ignored',literal=True)])
        scenario('future-authoritative',[call('list'),call('stat','generation'),call('open','generation','read'),call('open','generation','write')],[file(3,current),file(42,raw(dict(type='session',**dict(header,version=42),delegationDepth=0)))])
        scenario('unknown-required',[call('list'),call('stat','generation'),call('open','generation','read')],[file(3,current+raw(dict(type='foreign/required',seq=2,time=3,data={})))])
        scenario('unknown-ignorable',[call('open','generation','read'),call('read')],[file(3,current+raw(dict(type='foreign/info',seq=2,time=3,data={},ignorable=True)))])
        scenario('filename-header-disagreement',[call('list'),call('stat','generation'),call('open','generation','read')],[file(2,current)])
        scenario('stored-id-disagreement',[call('list'),call('stat','generation'),call('open','generation','read')],[file(3,current.replace('"generation"','"other"'))])
        scenario('duplicate-project',[call('list'),call('stat','generation'),call('open','generation','read')],[file(3,current),file(3,current,project='other')])
        scenario('duplicate-id',[call('list'),call('stat','generation'),call('open','generation','read')],[file(3,current),file(3,current.replace('"isSeeded":false','"cwd":"C:\\\\a","isSeeded":false'),project='--C-a--')])
        scenario('opposite-encoding-root',[call('stat','generation'),call('list'),call('create',header)],[dict(path='_no-cwd/generation/session.v3'+('.jsonl' if compression=='zstd' else '.jsonl.zstd'),raw=current,literal=True)])
        scenario('retired-flat-root',[call('list'),call('stat','generation'),call('create',header)],[dict(path='_no-cwd/generation'+suffix,raw=current,literal=True)])
        scenario('metadata-ignores-corrupt-body',[call('stat','generation'),call('list'),call('open','generation','read')],[file(3,current+raw(dict(type='turn/start',seq=2,time=3,data={})))])
        if compression=='none':
            scenario('raw-torn-repair',[call('open','generation','read',handle='r'),call('read',handle='r'),call('open','generation','write'),call('append',[dict(type='session/end-seed',seq=2,time=3,data={})]),call('read'),call('read',handle='r')],[file(3,current+'{"seq":2')])
        else:
            scenario('zstd-torn-repair',[call('open','generation','read',handle='r'),call('read',handle='r'),call('open','generation','write'),call('append',[dict(type='session/end-seed',seq=2,time=3,data={})]),call('read')],[file(3,current),dict(path='_no-cwd/generation/session.v3'+suffix,frames=['incomplete'],truncate=5)])
            # The physical tail is appended after mounting, preserving the header/body fixture.
            cases[-1]['files'].pop();cases[-1]['actions'].insert(0,dict(method='physical',append=True,file=dict(path='_no-cwd/generation/session.v3'+suffix,frames=['incomplete'],truncate=5)))
    return cases


if __name__=='__main__':
    cases=generate();Path(__file__).with_name('session_backend_cases.json').write_text(json.dumps(cases,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf8');print(len(cases))
