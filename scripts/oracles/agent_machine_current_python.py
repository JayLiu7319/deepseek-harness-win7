"""Actual candidate factory, model runtime and handle-backed machine observations."""
import asyncio
import json
import re
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from dsh.cordis.context import Context
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.core.session.json import UNDEFINED
from dsh.session.projections import SessionProjectionsPlugin
from dsh.core.system_prompt.current import CurrentSystemPrompt
from dsh.core.tools import ToolsPlugin
from dsh.core.agent_current import CurrentAgentPlugin
from dsh.core.agent_loop_current import CurrentAgentLoopPlugin
from dsh.llm.runtime_current import CurrentLlmRuntime
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin


class ScriptAdapter:
    def __init__(self,test):self.test=test;self.script=list(test.get('script',[]))
    async def resolve_model(self,provider,model,signal=None):
        info=dict(provider=provider,id=model,name=model)
        for key in ('reasoning','defaultMaxTokens','systemPromptUpdate'):
            if key in self.test:info[key]=self.test[key]
        return info
    async def stream(self,request):
        if not self.script:raise RuntimeError('MockAdapter: script exhausted')
        for chunk in self.script.pop(0):yield chunk


async def run(test,decode):
    ctx=Context();ids={};requests=[];notifications=[];results=[];errors=[]
    handle=None;agent=None;prompt=test.get('prompt','prompt one');route=test.get('options',dict(provider='script',model='model'));pre_step=test.get('preStep',{});retry=stopped=chunks=0
    def normalize(value,key=''):
        if value is UNDEFINED:return None
        if key=='signal':return '<signal>'
        if key=='agent':return value.id
        if isinstance(value,BaseException):
            result=dict(name=getattr(value,'name','TypeError' if isinstance(value,TypeError) else 'Error'),message=getattr(value,'message',str(value)))
            if hasattr(value,'code'):result['code']=value.code
            if getattr(value,'cause',None) is not None:result['cause']=normalize(value.cause)
            return result
        if isinstance(value,str) and re.fullmatch(r'[0-9a-f]{8}-[0-9a-f-]{27}',value,re.I):
            if value not in ids:ids[value]='generated:'+str(len(ids)+1)
            return ids[value]
        if isinstance(value,(tuple,list)):return [normalize(item) for item in value]
        if isinstance(value,dict):return {name:normalize(item,name) for name,item in value.items() if item is not UNDEFINED}
        return value
    def view():return normalize(dict(status=agent.status,events=agent.session.snapshotEvents(),messages=agent.session.deriveMessages(),inbox=ctx.get('sessionProjections').snapshot(agent.session)['values']['inbox']))
    with tempfile.TemporaryDirectory(prefix='dsh-machine-pair-') as folder,patch.object(CurrentSession,'_event_time',return_value=1000),patch('dsh.core.assistant_stream_current.time.time',return_value=1):
        try:
            for plugin in (CurrentLlmRuntime,CurrentSessionPlugin,SessionProjectionsPlugin,CurrentSystemPrompt,ToolsPlugin,CurrentAgentPlugin):await ctx.plugin(plugin)
            if test.get('persistence'):await ctx.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=folder,compression=test.get('compression','none')))
            await ctx.plugin(CurrentAgentLoopPlugin,dict(agents=[]))
            ctx.get('llm').registerAdapter(['script'],ScriptAdapter(test))
            async def assemble(assembly,context,next):
                result=dict(await next());result['sections']=[dict(name='test',text=prompt)];result['contexts']=[dict(name='policy',text=test['context'])] if test.get('context') else []
                return result
            async def propose(payload,next):return dict(await next(),**route)
            async def before_step(payload,next):
                if pre_step.get('kind')=='reject':return dict(kind='reject')
                result=dict(await next())
                if pre_step.get('empty'):result['messages']=[]
                if pre_step.get('startsRequestSeries'):result['startsRequestSeries']=True
                return result
            async def request_error(payload,next):
                nonlocal retry
                value=retry;retry+=1
                return dict(kind='retry') if value<test.get('retries',0) else await next()
            def stopping(payload):
                nonlocal stopped
                value=stopped;stopped+=1
                if value<len(test.get('stopping',[])):payload['agent'].inject(test['stopping'][value])
            def stream(request,next):requests.append(normalize(request));return next()
            ctx.on('system-prompt/assemble',assemble);ctx.on('agent/request',propose);ctx.on('agent/pre-step',before_step);ctx.on('agent/request-error',request_error);ctx.on('agent/turn-stopping',stopping);ctx.on('llm/stream',stream)
            def notify(name,payload):
                nonlocal chunks
                notifications.append(normalize(dict(name=name,payload=payload)))
                if name=='agent/assistant-stream' and payload['frame']['type']=='chunk' and test.get('cancelAfter'):
                    chunks+=1
                    if chunks==test['cancelAfter']:payload['agent'].cancel(dict(kind='user'))
                if name=='agent/session-start' and test.get('startMessage'):payload['agent'].followup(test['startMessage'])
            for name in ('agent/created','agent/disposed','agent/session-start','agent/status','agent/assistant-stream','agent/inbox/inserted','agent/inbox/discarded','agent/inbox/claimed'):
                if test.get('throwNotification')==name:
                    def fail(*args):raise RuntimeError('observer failure')
                    ctx.on(name,fail)
                ctx.on(name,lambda payload,key=name:notify(key,payload))
            ctx.on('agent/error',lambda payload:errors.append(normalize(payload['error'])))
            handle=await ctx.get('agents').create(dict(sessionId='machine',options=test.get('options',dict(provider='script',model='model')),meta=dict(createdAt=1000)));agent=handle.agent
            for action in test['actions']:
                try:
                    value=None;method=action['method']
                    if method=='prompt':prompt=action['text']
                    elif method=='route':route=action['config']
                    elif method=='preStep':pre_step=action['value']
                    elif method=='idle':await agent.whenIdle()
                    elif method=='view':value=view()
                    elif method=='resume':
                        await handle.dispose();handle=None
                        handle=await ctx.get('agents').resume(dict(resumeSessionId='machine',options=action.get('options',dict(provider='script',model='model'))));agent=handle.agent
                    elif method=='dispose':await handle.dispose();handle=None
                    else:value=getattr(agent,method)(*decode(action.get('args',[])))
                    results.append(dict(outcome='value',value=normalize(value)))
                except Exception as error:results.append(dict(outcome='error',error=normalize(error)))
            await agent.whenIdle();final=view()
            if handle is not None:await handle.dispose();handle=None
            return dict(results=results,final=final,requests=requests,notifications=notifications,errors=errors)
        finally:
            if handle is not None:await handle.dispose()
            await ctx.fiber.dispose()


def execute(test,decode):return asyncio.run(run(test,decode))
