"""System-head preservation, replacement tails and transaction replay."""
import json
from pathlib import Path
from scripts.oracles.generate_agent_loop_current_cases import message


def cases():
    rows=[]
    for system in (None,[],[dict(type='text',text='system head')]):
        for count in range(5):
            events=[]
            if system is not None:
                events.append(dict(type='system/message',data=dict(turn=1,step=1,message=dict(id='system',role='system',source=dict(kind='plugin',plugin='@deepseek-ai/dsh-system-prompt'),content=system)),intent=dict(surfaceOp='append')))
            for index in range(count):events.append(dict(type='user/message',data=message('input '+str(index)),intent=dict(surfaceOp='append')))
            rows.append(dict(case='head-%s/count-%s' % (str(system),count),kind='loop-current',operation='compaction',initial=events,retain=[0,10000,20000,100000],compact=True))
    head=dict(type='system/message',data=dict(turn=1,step=1,message=dict(id='system',role='system',source=dict(kind='plugin',plugin='@deepseek-ai/dsh-system-prompt'),content=[dict(type='text',text='head')])),intent=dict(surfaceOp='append'))
    assistant=dict(type='assistant/message',data=dict(turn=1,step=1,stream=[],message=dict(id='assistant',role='assistant',content=[dict(type='tool-call',id='call',name='test',arguments={})],source=dict(kind='model',provider='test',model='model'))),intent=dict(surfaceOp='append'))
    result=dict(type='tool/result',data=dict(turn=1,step=1,message=dict(id='result',role='user',source=dict(kind='tool',callId='call'),content=[dict(type='tool-result',toolCallId='call',content=[dict(type='text',text='result')])])),intent=dict(surfaceOp='append'))
    user=lambda text:dict(type='user/message',data=message(text),intent=dict(surfaceOp='append'))
    for retain in (10000,20000,30000):
        rows.append(dict(case='balanced-tool-cut-'+str(retain),kind='loop-current',operation='compaction',initial=[head,user('before'),assistant,result,user('tail')],retain=[retain],compact=True))
    return rows


if __name__=='__main__':
    Path(__file__).with_name('compaction_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
