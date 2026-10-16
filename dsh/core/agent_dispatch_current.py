"""Fused Agent-identity routing with non-vetoing rc.3 notifications."""
import asyncio
import contextvars
import inspect

from dsh.cordis.awaiting import resume_coroutine
from dsh.cordis.utils import _js_call_callback
from dsh.core.scope import scope_target


def agent_carrier(agent):
    return scope_target(agent, agent)


class AgentEventDispatch:
    def __init__(self, ctx, agent, carrier=None):
        self.ctx, self.agent = ctx, agent
        self.carrier = agent_carrier(agent) if carrier is None else carrier
        self.pending = set()

    def _fused(self, payload):
        return dict(payload, agent=self.agent)

    def _warn(self, name, failure, error):
        self.ctx.logger.warn('agent event "%s" listener %s: %s' % (name, failure, error))

    def _settle(self, result, name):
        if not inspect.isawaitable(result):
            return
        context = contextvars.copy_context()
        if inspect.iscoroutine(result):
            try:
                awaited = context.run(result.send, None)
            except StopIteration:
                return
            except BaseException as error:
                self._warn(name, 'rejected', error)
                return
            result = resume_coroutine(result, awaited)
        async def watch():
            try:
                await result
            except BaseException as error:
                self._warn(name, 'rejected', error)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            from dsh.cordis.events import _loopless_owner
            pending = asyncio.run_coroutine_threadsafe(watch(), _loopless_owner())
        else:
            pending = context.run(loop.create_task, watch())
        self.pending.add(pending)
        pending.add_done_callback(self.pending.discard)

    def emit(self, name, payload):
        fused = self._fused(payload)
        callbacks = self.ctx.events.dispatch('emit', [self.carrier, name, fused])
        for callback in callbacks:
            try:
                self._settle(_js_call_callback(callback, (fused,), maximum=1), name)
            except BaseException as error:
                self._warn(name, 'threw', error)

    async def serial(self, name, payload):
        return await self.ctx.serial(self.carrier, name, self._fused(payload))

    async def waterfall(self, name, payload, *rest):
        return await self.ctx.waterfall(self.carrier, name, self._fused(payload), *rest)


def agent_events(ctx, agent, carrier=None):
    return AgentEventDispatch(ctx, agent, carrier)


def emit_agent_event(ctx, agent, name, payload):
    agent_events(ctx, agent).emit(name, payload)


def assemble_context_for(agent, signal=None):
    result = dict(agent=agent, scope=agent)
    if signal is not None:
        result['signal'] = signal
    return result


agentCarrier = agent_carrier
agentEvents = agent_events
emitAgentEvent = emit_agent_event
assembleContextFor = assemble_context_for
