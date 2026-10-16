"""Frozen journeys for the rc.3 loop's durable projections and attempt frames."""
import json
from pathlib import Path


def message(identity, text=None, role='user', plugin=None):
    return dict(id=identity,role=role,content=[dict(type='text',text=text or identity)],
                source=dict(kind='plugin',plugin=plugin) if plugin else dict(kind='user'))


def action(method,*args,**extras):return dict(method=method,args=list(args),**extras)


def cases():
    rows=[]
    def add(name,operation,actions=None,**extras):
        rows.append(dict(case=name,kind='loop-current',operation=operation,actions=actions or [],**extras))
    a,b,c=message('a'),message('b'),message('c')
    prefix=[action('append','next-turn',a),action('append','next-step',b)]
    for operation,args in [('clear',[]),('claim',['next-turn',2]),('claim',['next-step',2]),
                           ('replace',['a',c]),('replace',['b',c]),('remove',['a']),('remove',['missing']),
                           ('replace',['a',b]),('append',['next-step',a]),('prepend',['next-turn',c])]:
        add('inbox-'+operation+'-'+str(len(rows)),'inbox',prefix+[action(operation,*args),action('state'),action('wire')])
    for start in [-100,-1.9,0,1.9,100,{'$scalar':'NaN'},{'$scalar':'Infinity'}]:
        for count in [-10,1.5,100,{'$scalar':'NaN'},{'$scalar':'Infinity'}]:
            add('inbox-splice-'+str(len(rows)),'inbox',prefix+[action('splice','next-turn',start,count,[c]),action('state')])
    for data in [dict(target='next-turn',start=0,removedCount=1,inserted=[]),
                 dict(target='next-turn',start=-1,inserted=[]),dict(target='next-turn',start=0.5,inserted=[])]:
        add('inbox-invalid-restore-'+str(len(rows)),'inbox',[action('state')],initial=[dict(type='agent/inbox/spliced',data=data)])
    add('inbox-duplicate-restore','inbox',[action('state')],initial=[dict(type='agent/inbox/spliced',data=dict(target=target,start=0,inserted=[a])) for target in ('next-turn','next-step')])
    add('inbox-inherited-prefix','inbox',[action('state'),action('append','next-turn',b),action('state')],options=dict(
        seed=[dict(seq=0,time=1000,type='agent/inbox/spliced',data=dict(target='next-turn',start=0,inserted=[a]))],
        meta=dict(isSeeded=True,parentSession='parent',createdAt=1000),inheritedEventCount=1))
    for in_history in (False,True):
        for starts_series in (False,True):
            decision=dict(inHistory=in_history,startsSeries=starts_series)
            for last in ('v1','v2',''):
                steps=[action('project','',decision,commit=True),action('project','v1',decision,commit=True),
                       action('appendEvent',event=dict(type='user/message',data=a,intent=dict(surfaceOp='append'))),
                       action('project',last,decision,commit=True),action('project',last,decision),action('reconstruct'),action('project',last,decision)]
                add('prompt-series-'+str(len(rows)),'system-prompt',steps)
    continuing=dict(inHistory=True,startsSeries=False)
    for last in ('v3',''):
        add('prompt-normalize-tails-'+str(len(rows)),'system-prompt',[
            action('project','v1',continuing,commit=True),action('project','v2',continuing,commit=True),
            action('project',last,dict(inHistory=False,startsSeries=False),commit=True),
            action('project',last,dict(inHistory=False,startsSeries=False))])
    nontext=message('system',role='system',plugin='@deepseek-ai/dsh-system-prompt');nontext['content']=[dict(type='reasoning',text='hidden')]
    add('prompt-nontext-head','system-prompt',[action('project','',continuing,commit=True),action('project','',continuing)],initial=[dict(type='system/message',data=dict(turn=1,step=1,message=nontext),intent=dict(surfaceOp='append'))])
    add('runtime-context-lifecycle','runtime-context',[
        action('project','',[],commit=True),action('project','context',[dict(name='policy',text='context')],commit=True),
        action('project','context',[]),action('reconstruct'),action('project','context',[]),
        action('project','',[],commit=True),action('project','',[])])
    owned=message('snapshot','retained',plugin='@deepseek-ai/dsh-system-prompt')
    add('runtime-replaced-and-restored','runtime-context',[action('project','retained',[]),
        action('appendEvent',event=dict(type='user/message',data=c,intent=dict(surfaceOp=dict(op='replace',startSeq=0,endSeq=0),sourceEventSeqs=[0]))),
        action('project','',[]),action('reconstruct'),action('project','',[])],initial=[dict(type='user/message',data=owned,intent=dict(surfaceOp='append'))])
    for finish in ['stop','max-tokens','error','aborted']:
        reason=dict(kind=finish)
        if finish in ('error','aborted'):reason['failure']=dict(code='FAILED',message='no')
        chunks=[dict(type='text-delta',index=0,text='one'),dict(type='text-delta',index=0,text='two'),dict(type='finish',reason=reason)]
        add('stream-'+finish,'stream',[action('start')]+[action('push',chunk) for chunk in chunks]+[action('snapshot'),action('settle'),action('snapshot')])
    for method in ['abandon','settle']:
        add('stream-failure-'+method,'stream',[action('start'),action('push',dict(type='text-delta',index=0,text='partial')),action(method,fail=True),action('snapshot')])
    add('stream-invalid-chunk','stream',[action('start'),action('push',dict(type='text-delta',index=-1,text='bad')),action('abandon'),action('snapshot')])
    for config in ({},{'includeHarnessIdentity':False,'personaPrefix':'prefix','personaSuffix':'suffix'},
                   {'persona':'retired','personaPrefix':'prefix','personaSuffix':'suffix'}):
        add('prompt-service-'+str(len(rows)),'prompt-service',config=config,sections=[dict(name='tool',order='TOOL_BASH',text='tool'),dict(name='source',order='HARNESS_SOURCE',text='source'),dict(name='web',order='WEB_SURFACE',text='web')])
    return rows


if __name__=='__main__':
    Path(__file__).with_name('agent_loop_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
