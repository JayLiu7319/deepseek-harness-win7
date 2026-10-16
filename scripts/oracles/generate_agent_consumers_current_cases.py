"""rc.3 persona and actual one-shot child driver journeys."""
import json
from pathlib import Path
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.generate_agent_loop_current_cases import action, message


def cases():
    rows=[]
    def add(name,actions,**extra):
        rows.append(dict(case=name,kind='machine-current',actions=actions,
            script=[response('answer') for _ in range(8)],realPrompt=True,
            promptConfig=dict(includeHarnessIdentity=False,personaPrefix='global prefix',personaSuffix='global suffix'),**extra))
    send=action('followup',message('parent input'));idle=action('idle')
    for config in (dict(prefix='local prefix'),dict(prefix='local prefix',suffix='local suffix'),
                   dict(prefix=''),dict(prefix='complete',suffix='ignored',complete=True),
                   dict(prefix='local prefix',includeRuntimeContext=False)):
        add('persona/'+str(len(rows)),[action('persona',config=config),send,idle])
    request=dict(label='child task',prompt=[dict(type='text',text='child task')],
                 descriptor=dict(version=3,mode='one-shot',provider='test',label='child task'))
    for fork in (False,True):
        for composition in ({},dict(persona='child persona'),dict(maxDepth=1),dict(outputSchema=dict(type='object'))):
            for prior in (False,True):
                add('child/'+str(len(rows)),([send,idle] if prior else [])+[
                    action('child',fork=fork,request=dict(request,**composition))])
    for depth in (0,-1,'invalid'):
        add('child/depth/'+str(depth),[action('child',request=dict(request,maxDepth=depth))])
    add('child/rejected-step',[action('child',request=request)],preStep=dict(kind='reject'))
    add('child/stream-attempt',[action('child',request=request)],cancelAfter=1)
    for compression in ('none','zstd'):
        add('child/durable/'+compression,[send,idle,action('resume'),action('child',fork=True,request=request)],persistence=True,compression=compression)
    add('child/structured-capture',[action('child',request=dict(request,outputSchema=dict(type='object',properties=dict(answer=dict(type='string')),required=['answer'],additionalProperties=False)))])
    rows[-1]['script']=[[dict(type='block-start',index=0,blockType='tool-call'),
        dict(type='tool-call-delta',index=0,id='capture',name='structured_output',argumentsDelta='{"answer":"captured"}'),
        dict(type='block-end',index=0,block=dict(type='tool-call',id='capture',name='structured_output',arguments='{"answer":"captured"}')),
        dict(type='finish',reason=dict(kind='tool-calls'))]]
    return rows


if __name__=='__main__':
    Path(__file__).with_name('agent_consumers_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
