"""Explicit filesystem journeys for the pinned generation runtime."""
import json
import copy
from pathlib import Path


def generate():
    cases=[]
    for compression in ['none','zstd']:
        for version in [0,1,2]:
            header=dict(type='session',version=version,id='generation',createdAt=1,delegationDepth=0)
            if version>=2:header['isSeeded']=False
            events=[dict(type='turn/start',seq=0,time=2,data=dict(turn=1)),
                dict(type='step/start',seq=1,time=3,data=dict(turn=1,step=1)),
                dict(type='request/header',seq=2,time=4,data=dict(reason='initial',header=dict(config=dict(provider='mock',model='mock'),system='system'))),
                dict(type='step/end',seq=3,time=5,data=dict(turn=1,step=1)),
                dict(type='turn/end',seq=4,time=6,data=dict(turn=1,reason=dict(kind='completed')))]
            raw=lambda rows:'\n'.join(json.dumps(row,separators=(',',':')) for row in rows)+'\n'
            base=dict(kind='generation',operation='prepare',compression=compression,version=version,raw=raw([header]+events))
            variants=[('prepare',{}),('publish',dict(publish=True)),('changed',dict(publish=True,changedSource=True)),
                ('different',dict(publish=True,target='different')),('same',dict(publish=True,target='same')),
                ('appended-winner',dict(publish=True,target='same',appendWinner=True)),
                ('verifier-drift',dict(publish=True,badDigest=True)),('header-reject',dict(failHeader=True)),
                ('header-only',dict(raw=raw([header]),publish=True)),
                ('byte-tail',dict(raw=raw([header])+ '{byte-torn')),
                ('broken-tail',dict(raw=raw([header])+'{broken\n')),
                ('broken-committed',dict(raw=raw([header])+'{broken\n'+raw([events[-1]]))),
                ('wrong-discriminator',dict(raw=raw([dict(header,version=version+1)]))),
                ('missing-version',dict(raw=raw([{k:v for k,v in header.items() if k!='version'}]))),
                ('negative-zero',dict(raw=raw([header]).replace('"version":'+str(version),'"version":-0'))),
                ('header-array',dict(raw='[]\n')),('header-broken',dict(raw='{broken\n'))]
            if compression=='zstd':
                variants += [('torn-frame',dict(tornFrame=True)),('combined-frame',dict(combinedFrame=True)),
                    ('complete-frame-torn-row',dict(raw=raw([header])+'{broken'))]
            for suffix,change in variants:
                cases.append(dict(base,case='generation/%s/v%s/%s'%(compression,version,suffix),**change))
        header=dict(type='session',version=3,id='generation',createdAt=1,isSeeded=False,delegationDepth=0)
        assistant=dict(turn=1,step=1,message=dict(id='assistant',role='assistant',content=[dict(type='text',text='hello')],
            source=dict(kind='model',provider='mock',model='mock',replayState=dict(response=dict(id='response')))),
            stream=[dict(type='text-chunks',time0=3,index=0,dt=[],texts=['hello']),
                dict(type='chunk',time=4,chunk=dict(type='usage',usage=dict(inputTokens=3,outputTokens=2))),
                dict(type='chunk',time=5,chunk=dict(type='finish',reason=dict(kind='stop'),replayState=dict(response=dict(id='response'))))],
            usage=dict(inputTokens=3,outputTokens=2))
        events=[dict(type='turn/start',seq=0,time=1,data=dict(turn=1)),
                dict(type='step/start',seq=1,time=2,data=dict(turn=1,step=1)),
                dict(type='assistant/message',seq=2,time=5,data=assistant,surfaceOp='append'),
                dict(type='step/end',seq=3,time=6,data=dict(turn=1,step=1)),
                dict(type='turn/end',seq=4,time=7,data=dict(turn=1,reason=dict(kind='completed')))]
        variants=[('valid',{},events),('wrong-id',dict(expectedId='other'),events),('wrong-count',dict(count=6),events),
                  ('header-only',dict(count=0),[])]
        for field in ['content','usage','replay']:
            bad=copy.deepcopy(events)
            if field=='content':bad[2]['data']['message']['content'][0]['text']='different'
            elif field=='usage':bad[2]['data']['usage']['inputTokens']=9
            else:bad[2]['data']['message']['source']['replayState']['response']['id']='other'
            variants.append((field,{},bad))
        for suffix,change,rows in variants:
            cases.append(dict(kind='generation',operation='verify',compression=compression,version=3,
                case='generation/%s/verify/%s'%(compression,suffix),raw=raw([header]+rows),**dict(dict(count=5),**change)))
    return cases


if __name__=='__main__':
    Path(__file__).with_name('session_generation_cases.json').write_text(json.dumps(generate(),ensure_ascii=True,separators=(',',':'))+'\n',encoding='utf-8')
