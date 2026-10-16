"""rc.3 Agent registry: explicit lineage and identity-scoped notifications."""
from dsh.core.agent import AgentRegistry, AgentPlugin
from dsh.core.agent_dispatch_current import agent_events, emit_agent_event
from dsh.cordis.utils import _js_call_callback


class CurrentAgentRegistry(AgentRegistry):
    def _factory_request_options(self, request):
        return dict(parent_agent=request.get('parentAgent', request.get('parent_agent')))

    def _emit_subject(self, name, agent):
        if name != 'agent/created':
            emit_agent_event(self.ctx, agent, name, {})
            return
        # Creation remains a synchronous veto boundary; only its returned
        # promise rejection is contained. Ordinary Agent notifications are not vetoes.
        dispatch = agent_events(self.ctx, agent)
        payload = dict(agent=agent)
        for callback in self.ctx.events.dispatch('emit', [dispatch.carrier, name, payload]):
            dispatch._settle(_js_call_callback(callback, (payload,), maximum=1), name)


class CurrentAgentPlugin(AgentPlugin):
    def apply(self, ctx):
        ctx.set_service('agents', CurrentAgentRegistry(ctx))
