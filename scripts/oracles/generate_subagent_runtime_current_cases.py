"""Actual rc.3 provider and continuation lifecycle journeys."""
import json
from pathlib import Path
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.generate_agent_loop_current_cases import action,message


def cases():
    rows=[]
    def add(name,actions,**extra):rows.append(dict(case=name,kind='machine-current',actions=actions,subagents=True,persistence=True,
        script=[response('answer') for _ in range(20)],realPrompt=True,promptConfig=dict(includeHarnessIdentity=False,personaPrefix='global prefix',personaSuffix='global suffix'),**extra))
    prompt=[dict(type='text',text='child initial')]
    wait=action('childIdle',id='worker');observe=action('childObserve',id='worker');parent=action('followup',message('parent input'));idle=action('idle')
    for provider in ('spawn','fork'):
        for compression in ('none','zstd'):
            spec=dict(provider=provider,label='worker label',childId='worker',request=dict(prompt=prompt,persona='worker persona'))
            add(provider+'/'+compression,[parent,idle,action('background',spec=spec),wait,observe,
                action('queueChild',id='worker',content=[dict(type='text',text='queued next')]),wait,observe,
                action('sendChild',id='worker',content=[dict(type='text',text='model message')]),wait,observe],compression=compression)
    for provider in ('spawn','fork'):
        add('one-shot/'+provider,[parent,idle,action('serviceChild',provider=provider,request=dict(prompt=prompt,label='once'))])
    for patch in (dict(maxDepth=0),dict(maxDepth=-1),dict(maxDepth='invalid'),dict(maxDepth=None),dict(maxDepth=False),dict(maxDepth=1.5),dict(maxDepth=-0.0)):
        add('depth/'+str(len(rows)),[action('background',spec=dict(provider='spawn',label='worker',childId='worker',request=dict(prompt=prompt,**patch)))])
    add('provider-absent',[action('background',spec=dict(provider='absent',label='worker',childId='worker',request=dict(prompt=prompt)))])
    add('cold-absent',[action('queueChild',id='absent',content=prompt)])
    spec=dict(provider='spawn',label='worker',childId='worker',request=dict(prompt=prompt))
    add('duplicate-cold',[action('background',spec=spec),wait,action('background',spec=spec)])
    for ancestor in (False,True):
        add('interrupt-park-and-wake/'+str(ancestor),[action('background',spec=spec),action('childEntered',id='worker'),
            action('queueChild',id='worker',content=[dict(type='text',text='parked')]),action('interruptChild',id='worker',ancestor=ancestor),
            action('childQuiescent',id='worker'),action('queueChild',id='worker',content=[dict(type='text',text='wake')]),wait,observe])
        rows[-1]['script']=['hang']+[response('answer') for _ in range(10)]
    add('wrong-parent-interrupt',[action('background',spec=spec),action('childEntered',id='worker'),
        action('interruptChild',id='worker',parentId='stranger'),action('interruptChild',id='worker'),wait,observe])
    rows[-1]['script']=['hang']+[response('answer') for _ in range(10)]
    return rows


if __name__=='__main__':
    Path(__file__).with_name('subagent_runtime_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
