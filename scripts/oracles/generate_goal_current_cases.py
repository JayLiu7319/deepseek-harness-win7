"""Deterministic rc.3 goal boundary inputs; expected values come from Source."""
import copy
import json
from pathlib import Path


def corpus():
    cases=[]
    def unit(name,**values):cases.append(dict(case='goal-'+name,kind='loop-current',operation='goal-units',**values))
    goal=dict(id='g',revision=1,objective='finish',phase='active',maxGoalRounds=2)
    create=dict(kind='goal/change',version=1,operation='create',goal=goal,roundsStarted=0,createdAt=1000,updatedAt=1000)
    def event(data,seq=0):return dict(type='goal/change',seq=seq,data=data)
    unit('create',mode='fold',events=[event(create)])
    unit('round',mode='fold',events=[event(create),dict(type='user/message',seq=1,data=dict(source=dict(kind='goal',goalId='g',revision=1,round=1)))])
    for operation,phase in [('pause','paused'),('resume','active'),('complete','complete'),('block','blocked'),('edit','active')]:
        change=dict(create,operation=operation,goal=dict(goal,revision=2,phase=phase))
        if operation=='block':change['goal']['blockedReason']=dict(code='model-reported',message='stuck')
        for suffix,alter in [('valid',{}),('stale',dict(goal=dict(change['goal'],revision=3))),('time',dict(updatedAt=999)),('counter',dict(roundsStarted=1))]:
            unit(operation+'-'+suffix,mode='fold',events=[event(create),event(dict(change,**alter),1)])
        unit(operation+'-missing',mode='fold',events=[event(change)])
    for name,change in [('clear',dict(kind='goal/change',version=1,operation='clear',cleared=dict(id='g',revision=2),clearedAt=1000)),
                        ('clear-backwards',dict(kind='goal/change',version=1,operation='clear',cleared=dict(id='g',revision=2),clearedAt=999))]:
        unit(name,mode='fold',events=[event(create),event(change,1),event(create,2)])
    invalid=[('kind',dict(create,kind='other')),('version',dict(create,version=2)),('null-version',dict(create,version=None)),
             ('operation',dict(create,operation='wrong')),('extra',dict(create,extra=True)),('time-type',dict(create,createdAt=True)),
             ('goal-null',dict(create,goal=None)),('goal-extra',dict(create,goal=dict(goal,extra=True))),
             ('objective',dict(create,goal=dict(goal,objective=' finish '))),('bom-objective',dict(create,goal=dict(goal,objective='\ufefffinish'))),
             ('round-limit',dict(create,goal=dict(goal,maxGoalRounds=0))),('phase',dict(create,goal=dict(goal,phase='unknown')))]
    for name,change in invalid:unit('invalid-'+name,mode='fold',events=[event(change),event(create,1)])
    for name,source in [('bad-id',dict(goalId='',revision=1,round=1)),('zero',dict(goalId='g',revision=1,round=0)),
                        ('stale',dict(goalId='g',revision=2,round=1)),('skip',dict(goalId='g',revision=1,round=2))]:
        unit('round-'+name,mode='fold',events=[event(create),dict(type='user/message',seq=1,data=dict(source=dict(kind='goal',**source)))])
    checkpoint=dict(current=dict(goal=goal,roundsStarted=0,createdAt=1000,updatedAt=1000),seenGoalIds=['g'],failure=None)
    unit('checkpoint-valid',mode='checkpoint',input=checkpoint)
    unit('checkpoint-empty',mode='checkpoint',input=dict(current=None,seenGoalIds=[],failure=None))
    for name,path,value in [('outer-extra',['extra'],1),('duplicate',['seenGoalIds'],['g','g']),('missing-id',['seenGoalIds'],[]),
         ('empty-failure',['failure'],''),('failure',['failure'],'invalid log'),('negative-time',['current','createdAt'],-1),
         ('backward-time',['current','updatedAt'],999),('excess-rounds',['current','roundsStarted'],3),
         ('unsafe-revision',['current','goal','revision'],9007199254740992),('safe-revision',['current','goal','revision'],9007199254740991),
         ('goal-extra',['current','goal','extra'],True),('current-extra',['current','extra'],True),
         ('untrimmed',['current','goal','objective'],' finish '),('empty-objective',['current','goal','objective'],''),
         ('reason',['current','goal','blockedReason'],dict(code='',message='',extra=True))]:
        data=copy.deepcopy(checkpoint);target=data
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
        unit('checkpoint-'+name,mode='checkpoint',input=data)
    def action(op,**kw):return dict(method='goal',operation=op,**kw)
    def machine(name,actions,**values):cases.append(dict(case='goal-machine-'+name,kind='machine-current',goals=True,actions=actions,**values))
    new=action('create',request=dict(objective='\ufeff finish \u00a0',maxGoalRounds=None))
    machine('lifecycle',[new,action('get'),action('resume'),action('disarm'),action('disarm'),action('resume'),action('pause'),action('resume'),action('block',reason=dict(code='test-block',message=' stuck ')),action('edit',request=dict(objective='changed')),action('complete'),action('clear'),dict(method='goalProjection')])
    machine('boundaries',[action('pause'),new,new,action('edit'),action('edit',request=dict(objective=' ')),action('edit',request=dict(maxGoalRounds=0)),action('pause'),action('pause'),action('block',reason=None),action('complete'),action('resume'),action('clear')])
    machine('stale',[new,action('pause',ref=dict(id='wrong',revision=9)),action('block',reason=dict(code='bad code',message='stuck')),action('block',reason=dict(code='fine',message='\ufeff ')),action('get')])
    machine('replay-failure',[new,dict(method='appendEvent',type='goal/change',data=dict(kind='goal/change',version=2)),dict(method='goalProjection'),action('get'),action('disarm'),dict(method='goalProjection')])
    machine('clear-armed',[new,action('clear'),action('get'),dict(method='goalProjection')])
    machine('cold-resume',[new,dict(method='resume'),action('get'),action('resume'),dict(method='goalProjection')],persistence=True)
    machine('driver-round-limit',[action('create',request=dict(objective='finish',maxGoalRounds=2)),dict(method='goalSettled',phase='blocked'),action('get'),dict(method='goalProjection')],goalDriver=True,script=[[dict(type='finish',reason=dict(kind='stop'))]]*2)
    start=action('create',request=dict(objective='finish',maxGoalRounds=2))
    done=[dict(type='text-delta',index=0,text='done'),dict(type='finish',reason=dict(kind='stop'))]
    machine('host-pause',[start,dict(method='entered'),action('pause'),dict(method='idle'),action('get')],goalDriver=True,script=['hang'])
    machine('pause-immediate-resume',[start,dict(method='entered'),action('pause'),action('resume'),dict(method='goalSettled',phase='blocked'),action('get')],goalDriver=True,script=['hang',done])
    machine('model-pause',[start,dict(method='entered'),dict(method='idle'),action('get')],goalDriver=True,modelPause=True,script=[done])
    human=dict(id='human',role='user',source=dict(kind='user'),content=[dict(type='text',text='finish')])
    for name,args in [('resume-paused',dict(action='resume')),('edit-empty',dict(action='edit')),('invalid-ref',dict(action='pause',revision=0)),
                      ('replacement',dict(action='pause',objective='bad')),('complete-reason',dict(action='complete',blocked_reason='bad'))]:
        machine('tool-'+name,[new,action('pause'),dict(method='followup',args=[human]),dict(method='entered'),
            dict(method='goalTool',name='update_goal',args=args),dict(method='cancel',args=[dict(kind='user')]),dict(method='idle'),action('get')],goalTools=True,script=['hang'])
    machine('tool-active-rearm',[new,action('disarm'),dict(method='followup',args=[human]),dict(method='entered'),
        dict(method='goalTool',name='update_goal',args=dict(action='resume')),dict(method='goalTool',name='get_goal'),
        dict(method='goalTool',name='update_goal',args=dict(action='pause')),dict(method='goalTool',name='update_goal',args=dict(action='resume')),
        dict(method='cancel',args=[dict(kind='user')]),dict(method='idle')],goalTools=True,script=['hang'])
    return cases


if __name__=='__main__':
    path=Path(__file__).with_name('goal_current_cases.json')
    path.write_text(json.dumps(corpus(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
