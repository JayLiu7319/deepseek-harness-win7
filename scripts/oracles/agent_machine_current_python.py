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
        entry=self.script.pop(0)
        hanging=entry=='hang' or isinstance(entry,dict) and 'hangAfter' in entry
        chunks=([dict(type='block-start',index=0,blockType='text'),dict(type='text-delta',index=0,text='partial')] if entry=='hang'
                else entry['hangAfter'] if hanging else entry)
        for chunk in chunks:yield chunk
        if hanging:
            future=asyncio.get_running_loop().create_future()
            def abort(*args):
                if not future.done():future.set_exception(RuntimeError('aborted'))
            remove=request['signal'].add_listener('abort',abort)
            if request['signal'].aborted:abort()
            try:await future
            finally:remove()


async def run(test,decode):
    ctx=Context();ids={};requests=[];notifications=[];results=[];errors=[]
    handle=None;agent=None;prompt=test.get('prompt','prompt one');route=test.get('options',dict(provider='script',model='model'));pre_step=test.get('preStep',{});retry=stopped=chunks=0
    def normalize(value,key=''):
        if value is UNDEFINED:return None
        if key=='signal':return '<signal>'
        if key=='agent':return normalize(value.id)
        if isinstance(value,BaseException):
            result=dict(name=getattr(value,'name','TypeError' if isinstance(value,TypeError) else 'Error'),message=getattr(value,'message',str(value)))
            if hasattr(value,'code'):result['code']=value.code
            if getattr(value,'cause',None) is not None:result['cause']=normalize(value.cause)
            return result
        if isinstance(value,str):
            def identity(match):
                name=match.group()
                if name not in ids:ids[name]='generated:'+str(len(ids)+1)
                return ids[name]
            return re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',identity,value,flags=re.I)
        if isinstance(value,(tuple,list)):return [normalize(item) for item in value]
        if isinstance(value,dict):return {name:normalize(item,name) for name,item in value.items() if item is not UNDEFINED}
        return value
    def view():return normalize(dict(status=agent.status,events=agent.session.snapshotEvents(),messages=agent.session.deriveMessages(),inbox=ctx.get('sessionProjections').snapshot(agent.session)['values']['inbox']))
    with tempfile.TemporaryDirectory(prefix='dsh-machine-pair-') as folder,patch.object(CurrentSession,'_event_time',return_value=1000),patch('dsh.core.assistant_stream_current.time.time',return_value=1):
        try:
            for plugin in (CurrentLlmRuntime,CurrentSessionPlugin,SessionProjectionsPlugin,CurrentSystemPrompt,ToolsPlugin,CurrentAgentPlugin):await ctx.plugin(plugin,test.get('promptConfig') if plugin is CurrentSystemPrompt else None)
            if test.get('persistence'):await ctx.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=folder,compression=test.get('compression','none')))
            if test.get('subagents'):
                from dsh.session.query_current import CurrentSqliteSessionQueryPlugin
                from dsh.subagent.runtime_current import CurrentSubagentPlugin
                from dsh.subagent.in_process_current import CurrentSpawnInProcess,CurrentForkInProcess
                await ctx.plugin(CurrentSqliteSessionQueryPlugin,dict(path=':memory:',openAt='never'))
                for plugin in (CurrentSubagentPlugin,CurrentSpawnInProcess,CurrentForkInProcess):await ctx.plugin(plugin)
                for name in ('subagent/start','subagent/end'):ctx.on(name,lambda payload,key=name:notifications.append(normalize(dict(name=key,payload=payload))))
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
            if not test.get('realPrompt'):ctx.on('system-prompt/assemble',assemble)
            ctx.on('agent/request',propose);ctx.on('agent/pre-step',before_step);ctx.on('agent/request-error',request_error);ctx.on('agent/turn-stopping',stopping);ctx.on('llm/stream',stream)
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
            handle=await ctx.get('agents').create(dict(sessionId='machine',agentOptions=test.get('options',dict(provider='script',model='model')),meta=dict(createdAt=1000)));agent=handle.agent
            for action in test['actions']:
                try:
                    value=None;method=action['method']
                    if method=='prompt':prompt=action['text']
                    elif method=='selectionSettings':
                        from dsh.subagent.model_selection import ModelSelectionSettings
                        await ctx.plugin(ModelSelectionSettings,action['config'])
                    elif method=='policySession':
                        session=ctx.get('sessions').create(action['id'])
                        session.append('subagent/model-selection-policy',dict(allowedModels=action['routes']))
                    elif method=='toolConfig':
                        from dsh.subagent.canonical_tools_current import apply_tool_subagent,CurrentToolSubagent
                        target=agent.session if action.get('direct',True) else None
                        if 'target' in action:
                            options=dict(action['target']);sid=options.pop('id');target=ctx.get('sessions').prepare(sid,options)
                        failures=[]
                        def install(runtime_ctx):
                            try:apply_tool_subagent(runtime_ctx,action['config'],target)
                            except Exception as error:failures.append(error)
                        await agent.ctx.inject(CurrentToolSubagent.inject,install)
                        if failures:raise failures[0]
                        value=ctx.get('tools').schemas(agent)
                        if 'target' in action:value=dict(schemas=value,events=target.snapshotEvents())
                    elif method=='toolCall':
                        from dsh.core.abort import AbortController
                        tool=ctx.get('tools').get(action.get('name','subagent'),agent)
                        value=await tool.execute(action['payload'],SimpleNamespace(agent=agent,signal=AbortController().signal))
                    elif method=='listChildren':value=await ctx.get('subagents').listChildren(agent.id)
                    elif method=='persona':
                        from dsh.core.persona_current import CurrentPersonaPlugin
                        await agent.ctx.plugin(CurrentPersonaPlugin,action['config'])
                    elif method=='child':
                        from dsh.core.abort import AbortController
                        from dsh.subagent.in_process_current import start_run
                        from dsh.subagent.descriptor import completed_turn_prefix
                        seed=completed_turn_prefix(agent) if action.get('fork') else None
                        run=await start_run(dict(action['request'],parent=agent,signal=AbortController().signal),seed if seed else None)
                        result=await run.result
                        value=normalize(dict(id=run.id,result=result,header=run.localAgent.session.header.to_dict(),events=run.localAgent.session.snapshotEvents(),owned=ctx.get('agents').isOwnedBy(run.id,agent)))
                        await run.dispose()
                    elif method=='background':
                        from dsh.core.abort import AbortController
                        spec=dict(action['spec'],signal=AbortController().signal,request=dict(action['spec']['request'],parent=agent))
                        value=await ctx.get('subagents').startContinuable(spec)
                    elif method=='childIdle':
                        async def closed():
                            while ctx.get('agents').get(action['id']) is not None:await asyncio.sleep(.001)
                        await asyncio.wait_for(closed(),3);await agent.whenIdle()
                    elif method=='childObserve':
                        observed=await ctx.get('sessionQuery').observeSession(action['id'])
                        try:value=dict(header=observed.header.to_dict(),events=observed.events,inheritedEventCount=observed.inheritedEventCount)
                        finally:observed.dispose()
                    elif method=='childEntered':
                        async def entered():
                            while not any(n.get('name')=='agent/assistant-stream' and n['payload']['agent']==action['id'] and n['payload']['frame']['type']=='chunk' and n['payload']['frame']['chunk']['type']=='text-delta' for n in notifications):await asyncio.sleep(.001)
                        await asyncio.wait_for(entered(),3)
                    elif method=='childQuiescent':
                        child=ctx.get('agents').get(action['id']);await child.whenIdle()
                        value=dict(status=child.status,events=child.session.snapshotEvents(),inbox=ctx.get('sessionProjections').snapshot(child.session,['inbox'])['values']['inbox'])
                    elif method=='interruptChild':ctx.get('subagents').interrupt(action['id'],dict(kind='ancestor',agent=agent) if action.get('ancestor') else dict(kind='user',parentSessionId=action.get('parentId',agent.id)))
                    elif method in ('queueChild','sendChild'):
                        from dsh.core.abort import AbortController
                        if method=='queueChild':value=await ctx.get('subagents')._deliver_prompt(agent,action['id'],action['content'],action.get('source',dict(kind='user')),AbortController().signal,'queue')
                        else:value=await ctx.get('subagents').sendMessage(agent,action['id'],action['content'],dict(signal=AbortController().signal))
                    elif method=='serviceChild':
                        from dsh.core.abort import AbortController
                        run=await ctx.get('subagents').start(action['provider'],dict(action['request'],parent=agent,signal=AbortController().signal))
                        try:value=dict(id=run.id,result=await run.result,header=run.localAgent.session.header.to_dict(),events=run.localAgent.session.snapshotEvents())
                        finally:await run.dispose()
                    elif method=='route':route=action['config']
                    elif method=='preStep':pre_step=action['value']
                    elif method=='idle':await agent.whenIdle()
                    elif method=='view':value=view()
                    elif method=='resume':
                        await handle.dispose();handle=None
                        handle=await ctx.get('agents').resume(dict(resumeSessionId='machine',agentOptions=action.get('options',dict(provider='script',model='model'))));agent=handle.agent
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
