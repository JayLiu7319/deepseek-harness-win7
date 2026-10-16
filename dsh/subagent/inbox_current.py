"""Activation-local cutoff around the Agent-owned durable inbox."""
import asyncio
import inspect
from dsh.cordis.awaiting import resume_coroutine
from dsh.subagent.errors import SubagentError


class SubagentInbox:
    def __init__(self,agent):
        self.agent,self.closing=agent,None

    @property
    def hasPending(self):
        return bool(self.agent.inbox.nextTurn or self.agent.inbox.nextStep)

    def deliver(self,message,delivery):
        if self.closing is not None:
            raise SubagentError('subagent "%s" activation is being disposed; the message was not accepted' % self.agent.id,'ACTIVATION_CLOSING')
        (self.agent.steer if delivery=='steer' else self.agent.followup)(message)

    def close(self,release):
        if self.closing is not None:return self.closing
        self.closing=asyncio.get_event_loop().create_future()
        # Publish admission cutoff before invoking the release's synchronous prefix.
        done=self.closing
        try:
            operation=release()
            if inspect.iscoroutine(operation):
                try:first=operation.send(None)
                except StopIteration as result:done.set_result(result.value);return done
                operation=resume_coroutine(operation,first)
            task=asyncio.ensure_future(operation)
        except BaseException as error:
            done.set_exception(error);return done
        def settled(task):
            if task.cancelled():done.cancel()
            elif task.exception() is not None:done.set_exception(task.exception())
            else:done.set_result(task.result())
        task.add_done_callback(settled)
        return done
