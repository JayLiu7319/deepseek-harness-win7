"""Actual driver journeys; expected results are frozen from the unchanged Source."""
import json
from pathlib import Path
from scripts.oracles.generate_agent_loop_current_cases import action, message


def response(text='ok',finish='stop'):
    return [dict(type='text-delta',index=0,text=text),dict(type='finish',reason=dict(kind=finish))]


def cases():
    rows=[]
    def add(name,actions,**extra):rows.append(dict(case=name,kind='machine-current',actions=actions,script=[response() for _ in range(8)],**extra))
    send=lambda identity:action('followup',message(identity))
    idle=action('idle');view=action('view')
    for capable in (False,True):
        for final in ('prompt one','prompt two',''):
            extra=dict(systemPromptUpdate='in-history') if capable else {}
            add('prompt/'+str(capable)+'/'+final,[send('one'),idle,action('prompt',text=final),send('two'),idle,view,send('three'),idle],**extra)
    for pre in (dict(kind='reject'),dict(empty=True),dict(startsRequestSeries=True)):
        add('pre-step/'+str(len(rows)),[send('one'),idle,view],preStep=pre)
    add('idle-inject-persists',[action('inject',message('context')),view,send('wake'),idle],context='runtime context')
    add('queued-turns',[send('one'),send('two'),idle,view])
    add('steering-before-request',[send('one'),action('steer',message('steer')),idle,view])
    add('cleared-wake-still-has-boundary',[send('one'),action('cancel',dict(kind='user')),idle,view])
    add('cancel-keep-inbox',[action('inject',message('context')),action('cancel',dict(kind='user'),dict(keepInbox=True)),view,send('wake'),idle])
    for notification in ('agent/session-start','agent/status','agent/assistant-stream','agent/disposed'):
        add('contained/'+notification,[send('one'),idle],throwNotification=notification)
    add('session-start-can-send',[idle,view],startMessage=message('startup'))
    for count in (1,2):
        add('stream-cancel/'+str(count),[send('one'),idle,view,send('later'),idle],cancelAfter=count)
    for compression in ('none','zstd'):
        add('resume/'+compression,[send('one'),idle,action('inject',message('retained')),action('resume'),view,send('two'),idle],persistence=True,compression=compression,systemPromptUpdate='in-history')
    add('defaults-re-resolved',[send('one'),idle,send('two'),idle],defaultMaxTokens=500,reasoning=dict(efforts=[dict(id='high',name='High')],defaultEffort='high'))
    add('route-error',[send('one'),idle],options={})
    add('stopping-adds-input',[send('one'),idle],stopping=[message('more')])
    rows[-1]['script']=[response(finish='max-tokens'),response()]
    failure=[dict(type='text-delta',index=0,text='failed prefix'),dict(type='finish',reason=dict(kind='error',failure=dict(message='retry me',code='FAILED')))]
    for retries in (0,1):
        add('request-error/'+str(retries),[send('one'),idle],retries=retries)
        rows[-1]['script']=[failure,response()]
    add('unknown-tool-result-followed-by-model',[send('one'),idle])
    rows[-1]['script']=[[dict(type='block-start',index=0,blockType='tool-call'),
        dict(type='tool-call-delta',index=0,id='call-one',name='missing',argumentsDelta='{}'),
        dict(type='block-end',index=0,block=dict(type='tool-call',id='call-one',name='missing',arguments='{}')),
        dict(type='finish',reason=dict(kind='tool-calls'))],response()]
    return rows


if __name__=='__main__':
    Path(__file__).with_name('agent_machine_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
