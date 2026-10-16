"""Inputs for declared-file native action authorization and wire errors."""
import json
from pathlib import Path
cases=[]
def add(name,**values):cases.append(dict(case=name,kind='present-open-current',**values))
add('open');add('reveal',query='?sessionId=child&seq=7&index=0&action=reveal')
add('host',path='/api/present.host',method='GET')
add('unavailable',unavailable=True);add('fallback',header={})
add('get-open',method='GET');add('post-host',path='/api/present.host');add('download',path='/api/present.download')
for i,query in enumerate(['','?seq=7&index=0','?sessionId=child&index=0','?sessionId=child&seq=7','?sessionId=child&seq=-1&index=0','?sessionId=child&seq=7&index=0.1','?sessionId=child&seq=9007199254740992&index=0','?sessionId=child&seq=7&index=9007199254740992','?sessionId=child&seq=7&index=1','?sessionId=child&seq=007&index=000','?sessionId=child&seq=7&index=0&action=delete','?sessionId=child&seq=7&index=0&action=','?sessionId=child&seq=7&index=0&index=1','?sessionId=child&seq=7&index=%D9%A0']):add('coordinates-'+str(i),query=query)
add('wrong-event',eventType='turn/start')
for i,data in enumerate([None,[],{},dict(turn=0,callId='c',files=[]),dict(turn=1.5,callId='c',files=[]),dict(turn=True,callId='c',files=[]),dict(turn=1,callId='',files=[]),dict(turn=1,callId='c',files=[None]),dict(turn=1,callId='c',files=[dict(path='')]),dict(turn=1,callId='c',files=[dict(path='\ufeff')]),dict(turn=1,callId='c',files=[dict(path='x',description=1)]),dict(turn=1.0,callId='c',files=[dict(path='../outside/file',description='External')])]):add('data-'+str(i),data=data)
for stage in ('read','stat','resolve','open'):add('failure-'+stage,failureStage=stage)
for code in ('SESSION_QUERY_SESSION_NOT_FOUND','SESSION_QUERY_EVENT_NOT_FOUND','ENOENT','ENOTDIR','SESSION_QUERY_CORRUPT_SESSION'):add('query-'+code,failureStage='read',code=code)
for code in ('session/not-found','workspace-file/not-found','workspace-file/not-regular-file','workspace-file/forbidden'):add('remote-'+code,failureStage='stat',remoteCode=code)
add('unmapped',unmapped=True);add('wrong-mapping',wrongMapping=True);add('pre-abort',aborted=True);add('mid-abort',abortDuring=True)
Path(__file__).with_name('present_open_current_cases.json').write_text(json.dumps(cases,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
