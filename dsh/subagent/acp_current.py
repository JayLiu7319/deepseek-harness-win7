"""ACP ownership after a subprocess handle has been published, including rejection."""
import asyncio

from dsh.core.abort import AbortController
from dsh.cordis.errors import AggregateError
from dsh.subagent.acp import AcpProvider, AcpRun, SubagentAcp, observe


async def dispose_acp_child(child, eof_grace_ms):
    failures = []
    if child.stdin is not None and not child.stdin.closed:
        child.stdin.close()
    controller = AbortController()
    timer = asyncio.get_running_loop().call_later(eof_grace_ms / 1000.0, controller.abort)
    try:
        try:
            exited = await child.wait_for_exit(controller.signal)
        except Exception as error:
            failures.append(error)
            exited = False
    finally:
        timer.cancel()
    if exited:
        return
    child.terminate()
    try:
        await child.wait_for_exit()
    except Exception as error:
        failures.append(error)
    if len(failures) == 1:
        raise failures[0]
    if failures:
        raise AggregateError(failures, 'ACP subprocess teardown failed')


class CurrentAcpRun(AcpRun):
    def __init__(self, *args):
        child = args[0]
        if child.stdin is None or child.stdout is None:
            raise RuntimeError('subagent-acp: subprocess implementation dropped a piped protocol stream')
        super().__init__(*args)
        self.starting = True
        self.process_failure = None
        self.process_rejected = asyncio.get_running_loop().create_future()
        self.process_rejected.add_done_callback(observe)
        def completed(done):
            if done.cancelled():
                return
            error = done.exception()
            if error is not None:
                self.process_failure = error
                self.process_rejected.set_exception(error)
        self.child.done.add_done_callback(completed)

    async def initialize(self, cwd):
        try:
            return await super().initialize(cwd)
        finally:
            self.starting = False

    async def race_cancel(self, operation):
        if not self.starting:
            return await super().race_cancel(operation)
        pending = asyncio.ensure_future(operation)
        pending.add_done_callback(observe)
        completed, _ = await asyncio.wait([pending, self.cancel_settled, self.process_rejected],
                                          return_when=asyncio.FIRST_COMPLETED)
        if self.cancel_settled in completed:
            raise RuntimeError('subagent cancelled while the ACP operation was running')
        if self.process_rejected in completed:
            return await self.process_rejected
        return await pending

    def startup_report_error(self, error):
        from dsh.subagent.acp import AcpRunFailure
        return error.cause if isinstance(error, AcpRunFailure) else self.process_failure or error

    def prompt_report_error(self, error):
        return self.process_failure or error

    async def teardown(self):
        await dispose_acp_child(self.child, self.config['disposeEofGraceMs'])
        await self.reader
        self.rpc.close()
        await self.rpc.drain()
        if self.child.stdout is not None:
            self.child.stdout.close()


class CurrentAcpProvider(AcpProvider):
    run_class = CurrentAcpRun

    async def prepare_child(self, child):
        # A returned handle owns its range even when its direct result rejects.
        return


class CurrentSubagentAcp(SubagentAcp):
    provider_class = CurrentAcpProvider
