"""Durable rc.3 continuation orchestration over one Activation registry."""
import asyncio
import uuid

from dsh.core.abort import NEVER_ABORTED
from dsh.core.agent import AgentOptions
from dsh.llm.message import create_user_message
from dsh.subagent.activation_current import ContinuableActivationRegistry
from dsh.subagent.composition import child_options,child_meta,capture_policy
from dsh.subagent.composition_current import assert_max_depth,resolve_depth
from dsh.core.session.json import UNDEFINED
from dsh.subagent.catalog_current import establish_catalog_child
from dsh.subagent.continuation_messages_current import createAgentMessage,withContinuableReturnGuidance
from dsh.subagent.descriptor import snapshot_descriptor,fold_descriptor
from dsh.subagent.internal import has_adjacent_message
from dsh.subagent.errors import SubagentError


def unavailable(sid,cause):
    error=SubagentError('subagent "%s" is unavailable' % sid,'NOT_RESUMABLE');error.cause=cause;return error


class CurrentContinuationManager:
    def __init__(self,ctx,host):
        self.ctx,self.host=ctx,host
        self.activations=ContinuableActivationRegistry(ctx,host.observe_activation)

    async def start(self,spec):
        request=spec['request'];parent=request['parent'];signal=spec.get('signal',NEVER_ABORTED);registry=self.activations
        registry.admitting(parent);persistence=self.ctx.get('sessionPersistence')
        if persistence is None:raise SubagentError('continuable subagents require session persistence (load a dsh-session-persistence backend)','PERSISTENCE_UNAVAILABLE')
        assert_max_depth(request.get('maxDepth',UNDEFINED));sid=spec.get('childId',str(uuid.uuid4()));registry.available(sid)
        depth=resolve_depth(parent,request.get('maxDepth'));options=child_options(parent,request.get('agentOptions'),depth)
        descriptor=dict(mode='continuable',provider=spec['provider'],label=spec['label'])
        for option,key in (('provider','agentProvider'),('model','agentModel'),('reasoningEffort','agentReasoningEffort')):
            value=getattr(options,option,None)
            if value is not None:descriptor[key]=value
        for key in ('persona','toolFilter'):
            if key in request:descriptor[key]=request[key]
        descriptor=snapshot_descriptor(descriptor);policy=capture_policy(parent)
        release=registry.hold_ownership(parent,sid)
        try:
            prepared=await self.host.prepare_continuable(spec['provider'],dict(sessionId=sid,parent=parent,signal=signal))
            signal.throwIfAborted();registry.admitting(parent);seed=prepared.get('seed')
            async with registry.locks.hold(sid):
                signal.throwIfAborted();registry.admitting(parent);registry.available(sid)
                if 'childId' in spec:
                    persisted=await persistence.stat(sid,dict(signal=signal));signal.throwIfAborted();registry.admitting(parent);registry.available(sid)
                    if persisted is not None:raise SubagentError('subagent "%s" already exists' % sid,'DUPLICATE_CHILD')
                activation=await registry.materialize(sid,spec['provider'],parent,options,request,signal,
                    dict(seed=seed,meta=child_meta(parent,depth,seed is not None),inheritedEventCount=len(seed or []),policy=policy,descriptor=descriptor))
                prompt=withContinuableReturnGuidance(parent.id,request['prompt']) if has_adjacent_message(self.ctx,activation.handle.agent) else request['prompt']
                message_id=await self.submit_materialized(activation,prompt,dict(source=dict(kind='user'),signal=signal,delivery='queue'),parent,
                    lambda:establish_catalog_child(parent.session,activation.handle.agent.session.header,descriptor))
            return dict(childId=sid,messageId=message_id)
        except BaseException:release();raise

    async def prepare_delivery(self,parent,sid,content,options):
        registry=self.activations;registry.admitting(parent);release=registry.hold_ownership(parent,sid)
        try:return await self.deliver_followup(parent,sid,content,options)
        except BaseException:release();raise

    async def deliver_followup(self,parent,sid,content,options):
        registry=self.activations;signal=options['signal']
        while True:
            async with registry.locks.hold(sid):
                a=registry.resident.get(sid)
                if a is None:return await self.cold_resume(parent,sid,content,options)
                if a.inbox.closing is not None:
                    await asyncio.gather(asyncio.shield(a.inbox.closing),return_exceptions=True)
                else:
                    if any(block.get('type')=='image' for block in content):
                        await self.assert_image_capable(a.handle.agent,signal)
                        if a.inbox.closing is not None:
                            await asyncio.gather(asyncio.shield(a.inbox.closing),return_exceptions=True);continue
                    identity=self.submit(a,content,options,parent);a.announced=True;return identity
            registry.admitting(parent);signal.throwIfAborted()

    def submit(self,a,content,options,parent):
        message=(create_user_message(dict(content=content,source=options['source'])) if 'source' in options else createAgentMessage(parent,content))
        return self.activations.submit(a,message,options['delivery'],parent,options['signal'])

    async def submit_materialized(self,a,content,options,parent,commit=None):
        try:
            if any(block.get('type')=='image' for block in content):
                await self.assert_image_capable(a.handle.agent,options['signal'])
                if a.inbox.closing is not None:raise SubagentError('subagent "%s" is closing' % a.id,'ACTIVATION_CLOSING')
            identity=self.submit(a,content,options,parent)
            if commit is not None:commit()
            a.announced=True;return identity
        except BaseException:
            try:await asyncio.shield(self.activations.dispose(a))
            except Exception as error:self.ctx.logger.warn('subagent continuation: disposal after admission or catalog append failure also failed: '+str(error))
            raise

    async def cold_resume(self,parent,sid,content,options):
        query=self.ctx.get('sessionQuery');signal=options['signal'];registry=self.activations
        if query is None:raise SubagentError('continuable subagents require session query (load @deepseek-ai/dsh-session-query)','CONTINUATION_UNAVAILABLE')
        try:source=await query.observeSession(sid,dict(signal=signal))
        except Exception as error:signal.throwIfAborted();raise unavailable(sid,error)
        try:
            registry.admitting(parent);registry.authorize(parent,sid,source.header.parentSession)
            descriptor=fold_descriptor(source.events[int(source.inheritedEventCount):])
            if descriptor is None or descriptor['mode']!='continuable':
                raise SubagentError('subagent "%s" has no supported continuation state and cannot be resumed; choose a different target' % sid,'NOT_RESUMABLE')
            try:
                a=await registry.materialize(sid,descriptor['provider'],parent,
                    AgentOptions(provider=descriptor.get('agentProvider'),model=descriptor.get('agentModel'),reasoningEffort=descriptor.get('agentReasoningEffort')),
                    descriptor,signal)
            except Exception as error:
                signal.throwIfAborted()
                if isinstance(error,SubagentError):raise
                raise unavailable(sid,error)
            return await self.submit_materialized(a,content,options,parent)
        finally:source.dispose()

    async def assert_image_capable(self,agent,signal):
        provider,model=agent.options.provider,agent.options.model;llm=self.ctx.get('llm')
        if provider is None or model is None or llm is None:return
        info=await llm.resolveModelInfo(provider,model,signal)
        if 'inputModalities' in info and 'image' not in info['inputModalities']:
            raise SubagentError('Model "%s" does not support image input.' % model,'MODEL_DOES_NOT_SUPPORT_IMAGES')

    async def send_message(self,sender,target,content,options):
        registry=self.activations
        if self.ctx.get('agents').get(sender.id) is not sender:raise SubagentError('message delivery requires the exact live sender agent','UNAUTHORIZED')
        registry.admitting(sender);a=registry.resident.get(sender.id)
        if a is not None and a.handle.agent is sender and a.parent==target:
            options['signal'].throwIfAborted()
            if a.inbox.closing is not None:raise SubagentError('subagent "%s" activation is being disposed; the message was not delivered' % sender.id,'ACTIVATION_CLOSING')
            parent=self.ctx.get('agents').get(target)
            if parent is None:raise SubagentError('direct parent is not live; the message was not delivered','PARENT_UNAVAILABLE')
            message=createAgentMessage(sender,content)
            try:registry.send_waking(parent,message,'steer')
            except Exception as cause:
                error=SubagentError('direct parent is not live; the message was not delivered','PARENT_UNAVAILABLE');error.cause=cause;raise error
            return message['id']
        if sender.session.header.parentSession==target:raise SubagentError('agent "%s" is not a resident continuable child and cannot send to parent "%s"' % (sender.id,target),'UNAUTHORIZED')
        return await self.prepare_delivery(sender,target,content,dict(signal=options['signal'],delivery='steer'))

    async def queue_prompt(self,parent,sid,content,source,signal):return await self.prepare_delivery(parent,sid,content,dict(source=source,signal=signal,delivery='queue'))
    async def steer_prompt(self,parent,sid,content,source,signal):return await self.prepare_delivery(parent,sid,content,dict(source=source,signal=signal,delivery='steer'))
    def interrupt(self,sid,authority):return self.activations.interrupt(sid,authority)
    async def drain(self):await self.activations.drain()
    async def drain_descendants(self,parents):await self.activations.drain_descendants(parents)
    async def drain_children(self,parent,ids):await self.activations.drain_children(parent,ids)
