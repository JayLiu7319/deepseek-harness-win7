"""Candidate units, exercised independently from Source values."""
import asyncio
import json
from types import SimpleNamespace


async def run(test,normalize):
    if test['operation']=='catalog':
        from dsh.subagent.catalog_current import CATALOG as d
        state=d['init']({},test.get('cut',0));results=[]
        for action in test['actions']:
            try:
                if action['method']=='apply':
                    old=state;state=d['apply'](state,action['event']);results.append(dict(accepted=True,changed=old is not state))
                elif action['method']=='checkpoint':state=d['stateSchema'](json.loads(json.dumps(state)));results.append(dict(accepted=True))
                elif action['method']=='state':results.append(dict(accepted=True,value=d['stateSchema'](action['value'])))
                elif action['method']=='view':results.append(dict(accepted=True,value=d['wire']['viewSchema'](action['value'])))
            except Exception:results.append(dict(accepted=False))
        return dict(results=results,state=state,view=d['wire']['view'](state))
    if test['operation']=='continuation-messages':
        from dsh.subagent.continuation_messages_current import createAgentMessage,createSettlementMessage,withContinuableReturnGuidance
        return normalize([createAgentMessage(SimpleNamespace(id=a['id']),a['content']) if a['method']=='relay'
            else withContinuableReturnGuidance(a['id'],a['content']) if a['method']=='guidance'
            else createSettlementMessage(a['id'],a['terminal']) for a in test['actions']])
    if test['operation']=='subagent-inbox':
        from dsh.subagent.inbox_current import SubagentInbox
        sent=[];trace=[];inbox=SimpleNamespace(nextTurn=[],nextStep=[])
        def send(value,delivery):
            sent.append([delivery,value]);(inbox.nextStep if delivery=='steer' else inbox.nextTurn).append(value)
        agent=SimpleNamespace(id='unit',inbox=inbox,steer=lambda v:send(v,'steer'),followup=lambda v:send(v,'queue'))
        unit=SubagentInbox(agent);unit.deliver(dict(id='one'),test['delivery']);before=unit.hasPending
        released=asyncio.get_event_loop().create_future()
        async def release():
            trace.append('release')
            try:unit.deliver(dict(id='reentry'),'queue')
            except Exception as error:trace.append(error.code)
            await released;trace.append('released')
        close=unit.close(release)
        async def duplicate():trace.append('duplicate release')
        again=unit.close(duplicate);trace.extend([close is again,unit.closing is close,unit.hasPending])
        if test.get('fail'):released.set_exception(RuntimeError('release failed'))
        else:released.set_result(None)
        try:await close;trace.append('fulfilled')
        except Exception as error:trace.append(str(error))
        return dict(sent=sent,before=before,trace=trace)
    raise ValueError('Unknown subagent unit')
