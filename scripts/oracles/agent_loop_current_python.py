"""Replay rc.3 loop-owned contracts with actual candidate Session and registry."""
import asyncio
import re
from types import SimpleNamespace
from unittest.mock import patch

from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.core.session.json import UNDEFINED
from dsh.session.projections import SessionProjectionsPlugin
from dsh.core.inbox_current import ReactLoopInbox
from dsh.core.runtime_context_current import SystemPromptProjection, RuntimeContextProjection
from dsh.core.assistant_stream_current import AssistantStreamAttempt
from dsh.core.system_prompt.current import CurrentSystemPrompt, FIRST_PARTY_SECTION_ORDER
from dsh.core.system_prompt import render_prompt


async def run(test, decode):
    ctx=Context();ids={};results=[];notifications=[];observations=[]
    def normalize(value):
        if value is UNDEFINED:return None
        if isinstance(value,str) and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f-]{27}',value,re.I):
            if value not in ids:ids[value]='generated:'+str(len(ids)+1)
            return ids[value]
        if isinstance(value,(tuple,list)):return [normalize(item) for item in value]
        if isinstance(value,dict):return {key:normalize(item) for key,item in value.items() if item is not UNDEFINED}
        return value
    def failure(error):
        value=dict(outcome='error',name=getattr(error,'name','TypeError' if isinstance(error,TypeError) else 'Error'),message=str(error))
        cause=getattr(error,'cause',None) or error.__cause__
        if cause is not None:value['cause']=str(cause)
        return value
    with patch.object(CurrentSession,'_event_time',return_value=1000),patch('dsh.core.assistant_stream_current.time.time',return_value=1):
        try:
            if test['operation'] in ('catalog','continuation-messages','subagent-inbox'):
                from scripts.oracles.subagent_units_current_python import run as units
                return await units(test,normalize)
            if test['operation']=='prompt-service':
                await ctx.plugin(CurrentSystemPrompt,test.get('config',{}))
                service=ctx.get('systemPrompt')
                for section in test.get('sections',[]):
                    value=dict(section)
                    if isinstance(value['order'],str):value['order']=service.getSectionOrder(value['order'])
                    service.section(value)
                assembly=await service.assemble({})
                orders={key:service.getSectionOrder(key) for key in ('HARNESS_IDENTITY','DEPLOYMENT_PERSONA_PREFIX','TOOL_BASH','HARNESS_SOURCE','WEB_SURFACE','DEPLOYMENT_PERSONA_SUFFIX')}
                return normalize(dict(orders=orders,assembly=assembly,rendered=render_prompt(assembly)))
            if test['operation']=='stream':
                revision=[0]
                def next_revision():revision[0]+=1;return revision[0]
                live=AssistantStreamAttempt('loop-pair',1,next_revision,1,2,lambda frame:notifications.append(normalize(frame)))
                for action in test['actions']:
                    try:
                        value=None
                        if action['method']=='settle':
                            def append():
                                if action.get('fail'):raise RuntimeError('append rejected')
                                observations.append('durable');return 7
                            live.settle(action.get('eventType','assistant/message'),append)
                        elif action['method']=='snapshot':value=dict(stream=live.stream,blocks=live.blocks(),interruptedBlocks=live.interruptedBlocks(),finish=live.finish,usage=live.usage,replayState=live.replayState,ended=live.ended)
                        else:value=getattr(live,action['method'])(*decode(action.get('args',[])))
                        results.append(dict(outcome='value',value=normalize(value)))
                    except Exception as error:results.append(failure(error))
                return dict(results=results,notifications=notifications,observations=observations)
            await ctx.plugin(CurrentSessionPlugin);await ctx.plugin(SessionProjectionsPlugin)
            session=ctx.get('sessions').create('loop-pair',decode(test.get('options',{})))
            for event in test.get('initial',[]):session.append(event['type'],event['data'],opts=event.get('intent'))
            def state():return dict(nextTurn=inbox.nextTurn,nextStep=inbox.nextStep,hasPending=inbox.hasPending)
            if test['operation']=='inbox':
                inbox=ReactLoopInbox(ctx.get('sessionProjections'),session,SimpleNamespace(emit=lambda name,payload:notifications.append(normalize(dict(name=name,payload=payload,state=state())))))
                target=inbox
                ctx.on('session/event',lambda subject,event:observations.append(normalize(dict(event=event,state=state()))) if subject is session else None)
            else:target=SystemPromptProjection(session) if test['operation']=='system-prompt' else RuntimeContextProjection(ctx,session)
            for action in test['actions']:
                try:
                    value=None
                    method=action['method']
                    if method=='appendEvent':
                        event=action['event'];value=session.append(event['type'],event['data'],opts=event.get('intent'))
                    elif method=='reconstruct':target=SystemPromptProjection(session) if test['operation']=='system-prompt' else RuntimeContextProjection(ctx,session)
                    elif method=='project':
                        value=target.project(*decode(action['args']));snapshot=normalize(value)
                        if action.get('commit'):
                            if test['operation']=='system-prompt':
                                for decision in value:session.append('system/message',dict(turn=1,step=1,message=decision['message']),opts=decision['intent'])
                            elif value is not None:session.append('user/message',value,'append')
                        value=snapshot
                    elif method=='state':value=state()
                    elif method=='wire':value=ctx.get('sessionProjections').snapshot(session)
                    else:value=getattr(target,method)(*decode(action.get('args',[])))
                    results.append(dict(outcome='value',value=normalize(value)))
                except Exception as error:results.append(failure(error))
            return normalize(dict(results=results,notifications=notifications,observations=observations,events=session.snapshotEvents(),surface=session.surface.nodes,messages=session.deriveMessages()))
        finally:await ctx.fiber.dispose()


def execute(test,decode):return asyncio.run(run(test,decode))
