"""Candidate Agent write ownership and publication against v3 handles.

The request driver migrates separately; no active profile mounts this service yet.
"""
import asyncio
import copy
import inspect
import uuid

from dsh.cordis.errors import AggregateError
from dsh.core.agent_factory import FactoryTransaction
from dsh.core.agent_loop import AgentLoopService, AgentLoopPlugin
from dsh.core.configured_agents import ConfiguredStartup
from dsh.core.session.json import UNDEFINED
from dsh.core.session.preparation import SessionPreparation
from dsh.core.session.repair import interruptedTurnClosers
from dsh.session.persistence import SessionPersistenceNotFoundError


class CurrentFactoryTransaction(FactoryTransaction):
    def __init__(self,*args,**kwargs):
        self.stored=None
        super().__init__(*args,**kwargs)

    async def _dispose(self,owner_triggered):
        failures=[]
        for remove in self.listeners:remove()
        self.listeners.clear()
        try:
            try:
                if self.agent is not None:self.agent.cancel(dict(kind='disposed'))
                if self.driver is not None:
                    await self.agent.when_idle()
                    self.driver.cancel()
                    await asyncio.gather(self.driver,return_exceptions=True)
                    if self.driver in self.factory._active_tasks:self.factory._active_tasks.remove(self.driver)
                if self.scope is not None:await self.scope.dispose()
            except BaseException as error:failures.append(error)
            try:
                if self.stored is not None:await self.stored['handle'].close()
            except BaseException as error:failures.append(error)
            for detach in (self.detach_agent,self.detach_session):
                try:
                    if detach is not None:detach()
                except BaseException as error:failures.append(error)
        finally:
            self.factory._transactions.discard(self)
            if not owner_triggered and self.unfollow is not None:
                try:
                    result=self.unfollow()
                    if inspect.isawaitable(result):await result
                except BaseException as error:failures.append(error)
        if len(failures)==1:raise failures[0]
        if failures:raise AggregateError(failures,'agent "%s" disposal failed' % self.sid)


class CurrentConfiguredStartup(ConfiguredStartup):
    async def restore(self,row,options,meta,persistence,explicit=False):
        sid=row['resumeSessionId'] if explicit else row['sessionId']
        try:
            if not explicit:await self.wait_released(sid)
            if not self.active():return
            try:
                await self.factory.resume(sid,options,owner_ctx=self.ctx,persistence=persistence)
                return
            except Exception as error:
                if not self.active():return
                if explicit or not isinstance(error,SessionPersistenceNotFoundError):raise
            if self.active():await self.factory.create_agent(sid,options,meta,owner_ctx=self.ctx)
        except Exception as error:self.report(row['id'],'resume' if explicit else 'restore',sid,error)


class CurrentAgentLifecycleService(AgentLoopService):
    def __init__(self,ctx,config=None):
        super().__init__(ctx,config)
        self._configured=CurrentConfiguredStartup(self)

    async def _before_publish(self,tx,session):
        await self.appendUnstoredSuffix(tx.stored,session)

    def _invoke_setup(self,setup,agent):
        from dsh.cordis.utils import _js_call_callback
        return _js_call_callback(setup,(agent.ctx,agent))

    async def createStoredSession(self,session,signal=None):
        persistence=self.ctx.get('sessionPersistence')
        if persistence is None:return None
        options=dict(inheritedEventCount=session.inheritedEventCount)
        if signal is not None:options['signal']=signal
        return dict(handle=await persistence.create(session.header,options),storedCount=0)

    async def appendUnstoredSuffix(self,stored,session):
        if stored is None:return
        suffix=session.snapshotEvents(stored['storedCount'])
        if suffix:await stored['handle'].append(suffix)
        stored['storedCount']+=len(suffix)

    @staticmethod
    def _validate_options(options):
        maximum=getattr(options,'max_tokens',None)
        if maximum is not None and (type(maximum) not in (int,float) or not 1<=maximum<=9007199254740991 or int(maximum)!=maximum):
            raise TypeError('agent maxTokens must be a positive safe integer')

    async def _rollback(self,tx):
        try:await tx.dispose()
        except BaseException:pass

    async def create_agent(self,session_id=None,options=None,meta=None,setup=None,seed=None,signal=None,
                           owner_ctx=None,inherited_event_count=UNDEFINED):
        sid=session_id if session_id is not None else 'session-'+uuid.uuid4().hex[:8]
        tx=CurrentFactoryTransaction(self,owner_ctx or self.ctx,sid,signal)
        wrapper=asyncio.get_running_loop().create_future();self._wrappers.add(wrapper)
        preparation=None
        try:
            preparation=SessionPreparation.create(self.ctx.get('sessions').prepare(sid,
                seed=seed,meta=meta,inheritedEventCount=inherited_event_count))
            tx.stored=await tx.race(lambda:self.createStoredSession(preparation.session,signal),
                                   lambda late:None if late is None else late['handle'].close())
            self._validate_options(options)
            return await self._publish_preparation(tx,preparation,options,setup,'startup')
        except BaseException:
            await self._rollback(tx)
            raise
        finally:
            if preparation is not None:preparation.dispose()
            self._wrappers.discard(wrapper)
            if not wrapper.done():wrapper.set_result(None)
    create=create_agent

    async def resume(self,resume_session_id,options=None,setup=None,signal=None,owner_ctx=None,persistence=None):
        sid=resume_session_id
        persistence=persistence if persistence is not None else self.ctx.get('sessionPersistence')
        if persistence is None:
            raise RuntimeError('cannot resume: session persistence is not configured (load a dsh-session-persistence backend)')
        tx=CurrentFactoryTransaction(self,owner_ctx or self.ctx,sid,signal)
        wrapper=asyncio.get_running_loop().create_future();self._wrappers.add(wrapper)
        preparation=None
        try:
            handle=await tx.race(lambda:persistence.open(sid,'write',dict(signal=tx.controller.signal)),lambda late:late.close())
            tx.stored=dict(handle=handle,storedCount=0)
            read=await tx.race(lambda:handle.read(options=dict(signal=tx.controller.signal)))
            persisted=read['events'];closers=interruptedTurnClosers(persisted)
            if closers:await handle.append(closers)
            preparation=SessionPreparation.create(self.ctx.get('sessions').prepare(sid,
                seed=list(persisted)+closers,meta=copy.deepcopy(handle.header),inheritedEventCount=handle.inheritedEventCount,
                eventState=read['eventState']))
            tx.stored['storedCount']=len(persisted)+len(closers)
            await self.appendUnstoredSuffix(tx.stored,preparation.session)
            tx.assert_live();self._validate_options(options)
            return await self._publish_preparation(tx,preparation,options,setup,'resume')
        except BaseException:
            await self._rollback(tx)
            raise
        finally:
            if preparation is not None:preparation.dispose()
            self._wrappers.discard(wrapper)
            if not wrapper.done():wrapper.set_result(None)


class CurrentAgentLifecyclePlugin(AgentLoopPlugin):
    _service_class=CurrentAgentLifecycleService
