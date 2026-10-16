"""Real model-facing definitions and their handle-backed child consumers."""
import json
from pathlib import Path
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.generate_agent_loop_current_cases import action, message


def cases():
    rows=[]
    settings=action('selectionSettings',config=dict(enabled=True,allowedModels=[dict(provider='script',model='model')]))
    config=dict(provider='spawn',enableRunInBackground=False)
    call=action('toolCall',payload=dict(description='child task',prompt='tool input'))
    def add(name,actions):
        rows.append(dict(case=name,kind='machine-current',subagents=True,persistence=True,
                         script=[response('answer') for _ in range(20)],actions=actions))
    for provider in ('spawn','fork'):
        for selectable in (False,True):
            for direct in (False,True):
                selected=dict(config,provider=provider,modelSelectionSettings=selectable)
                actions=[settings] if selectable else []
                actions += [action('toolConfig',config=selected,direct=direct),call,action('listChildren')]
                add('%s/selection-%s/direct-%s' % (provider,selectable,direct),actions)
    for maximum in (0,-1,None,False,1.5,-0.0):
        add('depth-'+str(len(rows)),[action('toolConfig',config=dict(config,maxDepth=maximum))]+([call] if type(maximum) is int and maximum==0 else []))
    add('missing-settings',[action('toolConfig',config=dict(config,modelSelectionSettings=True))])
    add('selection-allowed',[settings,action('toolConfig',config=dict(config,modelSelectionSettings=True)),
        action('toolCall',name='list_subagent_models',payload={}),
        action('toolCall',payload=dict(call['payload'],provider='script',model='model'))])
    add('selection-denied',[settings,action('toolConfig',config=dict(config,modelSelectionSettings=True)),
        action('toolCall',payload=dict(call['payload'],provider='other',model='model'))])
    add('resume-fixed-definition',[action('followup',message('first')),action('idle'),action('resume'),settings,
        action('toolConfig',config=dict(config,modelSelectionSettings=True)),call])
    selected=dict(config,modelSelectionSettings=True)
    add('unpublished-session-only-parent',[settings,
        action('policySession',id='session-only',routes=[dict(provider='inherited',model='parent-route')]),
        action('toolConfig',config=selected,target=dict(id='unpublished',meta=dict(origin='subagent',parentSession='session-only')))])
    add('unpublished-child-without-parent-policy',[settings,
        action('toolConfig',config=selected,target=dict(id='unpublished',meta=dict(origin='subagent',parentSession='missing')))])
    add('empty-seed-is-not-fresh',[settings,action('toolConfig',config=selected,target=dict(id='seeded-empty',seed=[]))])
    return rows


if __name__=='__main__':
    Path(__file__).with_name('subagent_tools_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
