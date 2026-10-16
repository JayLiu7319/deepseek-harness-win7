"""rc.3 provider seam, parent catalog commit and continuable ownership."""
from dsh.cordis.plugin import Plugin
from dsh.typert.remote import TypertRemoteService, Remote
from dsh.core.tools import _assert_supported_schema
from dsh.subagent.catalog_current import CATALOG,establish_catalog_child
from dsh.subagent.continuation_current import CurrentContinuationManager
from dsh.subagent.composition_current import assert_max_depth
from dsh.core.session.json import UNDEFINED
from dsh.subagent.descriptor import snapshot_descriptor
from dsh.subagent.errors import SubagentError
from dsh.subagent.lifecycle_current import LifecycleEmitter,ActivationObserver,observe_run
from dsh.subagent.projections import IDENTITY,TIMING


class CurrentSubagentRuntime(TypertRemoteService):
    def __init__(self,ctx):
        super().__init__(ctx,'subagents')
        self.providers={};self.emit_lifecycle=LifecycleEmitter(self.ctx,self)
        self.continuations=None
        def bind(child_ctx):
            manager=CurrentContinuationManager(child_ctx,self);self.continuations=manager
            def clear():
                if self.continuations is manager:self.continuations=None
            child_ctx.effect(lambda:clear,'subagents.continuationBinding()')
        ctx.inject(['agents'],bind)

    def require_continuations(self):
        if self.continuations is None:raise SubagentError('continuable subagents require the agents service','CONTINUATION_UNAVAILABLE')
        return self.continuations

    def registerProvider(self,provider):
        def setup():
            if provider.name in self.providers:raise SubagentError('a subagent provider named "%s" is already registered' % provider.name,'DUPLICATE_PROVIDER')
            self.providers[provider.name]=provider
            def remove():
                self.providers.pop(provider.name,None);self.emit_lifecycle('subagent/provider-removed',provider.name)
            yield remove
            self.ctx.emit('subagent/provider-added',provider)
        return self.ctx.effect(setup,'subagents.registerProvider()')

    def getProvider(self,name):return self.providers.get(name)
    def list(self):return list(self.providers)
    def expect_provider(self,name):
        provider=self.getProvider(name)
        if provider is None:raise SubagentError('no subagent provider registered for "%s"' % name,'NO_PROVIDER')
        return provider

    def observe_activation(self,provider,sid,parent):return ActivationObserver(self.emit_lifecycle,provider,sid,parent)

    async def prepare_continuable(self,name,request):
        provider=self.expect_provider(name);prepare=getattr(provider,'prepareContinuable',None)
        if prepare is None:raise SubagentError('subagent provider "%s" does not support continuable children (no prepareContinuable capability)' % provider.name,'UNSUPPORTED_CAPABILITY')
        return await prepare(request)

    async def start(self,name,request):
        provider=self.expect_provider(name)
        for key,capability in (('agentOptions','agentOptions'),('outputSchema','outputSchema'),('maxDepth','depthLimit'),('toolFilter','toolFilter'),('persona','persona')):
            if key in request and not provider.capabilities.get(capability):
                raise SubagentError('subagent provider "%s" does not support the "%s" capability' % (name,capability),'UNSUPPORTED_CAPABILITY')
        assert_max_depth(request.get('maxDepth',UNDEFINED))
        if 'outputSchema' in request:
            _assert_supported_schema(request['outputSchema'])
            if request['outputSchema'].get('type')!='object':raise TypeError('subagent outputSchema must be an object schema')
        descriptor=snapshot_descriptor(dict(mode='one-shot',provider=name,**(dict(label=request['label']) if 'label' in request else {})))
        run=await provider.start(dict(request,descriptor=descriptor))
        if getattr(run,'localAgent',None) is not None:
            try:establish_catalog_child(request['parent'].session,run.localAgent.session.header,descriptor)
            except BaseException:
                try:await run.dispose()
                except Exception as error:self.ctx.logger.warn('subagent: disposal after catalog append failure also failed: '+str(error))
                raise
        return observe_run(self.emit_lifecycle,name,request['parent'],run)

    async def startContinuable(self,spec):return await self.require_continuations().start(spec)
    async def sendMessage(self,sender,target,content,options):return await self.require_continuations().send_message(sender,target,content,options)
    async def _deliver_prompt(self,parent,sid,content,source,signal,delivery):
        manager=self.require_continuations()
        return await (manager.steer_prompt if delivery=='steer' else manager.queue_prompt)(parent,sid,content,source,signal)
    def interrupt(self,sid,authority):
        if self.continuations is not None:return self.continuations.interrupt(sid,authority)
    async def drainContinuableDescendants(self,parents):
        if self.continuations is not None:await self.continuations.drain_descendants(parents)
    async def drainContinuableChildren(self,parent,ids):
        if self.continuations is not None:await self.continuations.drain_children(parent,ids)
    async def listChildren(self,sid,signal=None):
        from dsh.subagent.listing import list_children
        return await list_children(self.ctx,sid,signal)
    async def listDescendants(self,sid,signal=None):
        from dsh.subagent.listing import list_children
        return await list_children(self.ctx,sid,signal,descendants=True)

    @Remote('list')
    async def remoteExportList(self, parentSessionId, signal):
        from dsh.subagent.remote_current import catalog
        return await catalog(self, parentSessionId, signal)

    @Remote('prompt')
    async def prompt(self, request, signal):
        from dsh.subagent.remote_current import prompt
        return await prompt(self, request, signal)

    @Remote('interruptByParent')
    def interruptByParent(self, childSessionId, parentSessionId, mode):
        from dsh.subagent.remote_current import interrupt
        return interrupt(self, childSessionId, parentSessionId, mode)


class CurrentSubagentPlugin(Plugin):
    id='subagent'

    def apply(self,ctx):
        service=CurrentSubagentRuntime(ctx);ctx.set_service('subagents',service)
        def projections(child_ctx):
            for definition in (CATALOG,TIMING,IDENTITY):child_ctx.get('sessionProjections').register(definition)
        ctx.inject(['sessionProjections'],projections)
