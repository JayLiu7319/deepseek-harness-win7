"""Finite attribution, catalog checkpoint, and admission journeys."""
import json
from pathlib import Path


def cases():
    rows=[]
    def add(name,operation,actions,**extra):rows.append(dict(case=name,kind='loop-current',operation=operation,actions=actions,**extra))
    def fact(i,**extra):return dict(version=0,childId='child-'+str(i),childCreatedAt=200-i,mode='one-shot',**extra)
    def event(i,data=None):return dict(type='subagent/catalog',seq=i,time=0,data=data if data is not None else fact(i))
    for length in (0,1,63,64,65,130):
        add('catalog/rollover/'+str(length),'catalog',[dict(method='apply',event=event(i)) for i in range(length)]+[dict(method='checkpoint')])
    for cut in (0,1,2,3):
        add('catalog/cut/'+str(cut),'catalog',[dict(method='apply',event=event(i,dict(version=0,childId='same',childCreatedAt=1,mode='continuable',label='task'))) for i in range(3)],cut=cut)
    for patch in (dict(version=9),dict(childId=1),dict(childCreatedAt=-1),dict(childCreatedAt=0.5),dict(mode='continuable'),dict(label=None),dict(extra=True),dict(version=False)):
        add('catalog/reject/'+str(len(rows)),'catalog',[dict(method='apply',event=event(0,dict(fact(0),**patch)))])
    for node in (None,dict(values=[]),dict(values=[fact(0)]*65),dict(values=[fact(0)],extra=True),dict(values=[fact(0)],previous=None)):
        add('catalog/checkpoint-reject/'+str(len(rows)),'catalog',[dict(method='state',value=dict(inheritedEventCount=0,head=node))])
    for row in (dict(id='one',createdAt=1,mode='one-shot'),dict(id='two',createdAt=1,mode='continuable',label='later'),dict(id='bad',createdAt=1,mode='continuable'),dict(id='bad',createdAt=1,mode='one-shot',extra=True)):
        add('catalog/view/'+str(len(rows)),'catalog',[dict(method='view',value=[row])])
    for reason in ('completed','aborted','max-tokens','refusal','error','external-end'):
        for output in (None,[],[dict(type='text',text='answer')]):
            terminal=dict(stopReason=reason)
            if output is not None:terminal['output']=output
            add('message/settlement/'+str(len(rows)),'continuation-messages',[dict(method='settlement',id='child',terminal=terminal)])
    for identity in ('ordinary','quoted"\nidentity','x'*200,'\U0001f642'*80):
        add('message/identity/'+str(len(rows)),'continuation-messages',[
            dict(method='relay',id=identity,content=[dict(type='text',text='body')]),
            dict(method='guidance',id=identity,content=[]),
            dict(method='settlement',id=identity,terminal=dict(stopReason='completed'))])
    for delivery in ('queue','steer'):
        for fail in (False,True):add('inbox/'+delivery+'/'+str(fail),'subagent-inbox',[],delivery=delivery,fail=fail)
    return rows


if __name__=='__main__':
    Path(__file__).with_name('subagent_units_current_cases.json').write_text(json.dumps(cases(),ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
