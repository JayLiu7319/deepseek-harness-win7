"""Instance-owned image compression slots and shared, cancellable generations."""
import asyncio

from dsh.cordis.errors import ThrownValueError
from dsh.core.abort import AbortController
from dsh.attachment.immutable_current import check_abort


def compression_failure(error):
    if not isinstance(error, ThrownValueError):
        return error
    result = RuntimeError('Image compression task rejected with a non-Error value.')
    result.cause = error.value
    return result


def abort_reason(signal):
    if isinstance(signal.reason, BaseException):
        return signal.reason
    error = RuntimeError('Attachment request cancelled with a non-Error reason.')
    error.cause = signal.reason
    return error


class CompressionLimiter:
    def __init__(self, concurrency):
        self.concurrency = concurrency
        # Python 3.8 binds primitives eagerly; service construction is also
        # valid before its owning event loop has started.
        self._slots = None

    async def run(self, task):
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.concurrency)
        async with self._slots:
            try:
                return await task()
            except Exception as error:
                raise compression_failure(error)


class SharedRequest:
    def __init__(self, start):
        self.controller = AbortController()
        self.waiters = 0
        self.task = asyncio.ensure_future(start(self.controller.signal))
        # An abandoned last waiter must not leave an unobserved task rejection.
        self.task.add_done_callback(lambda done: None if done.cancelled() else done.exception())

    async def wait(self, signal=None):
        check_abort(signal)
        self.waiters += 1
        released = False
        def release(cancelled):
            nonlocal released
            if released:
                return
            released = True
            self.waiters -= 1
            if cancelled and self.waiters == 0 and not self.task.done():
                self.controller.abort(abort_reason(signal) if signal is not None and signal.aborted else RuntimeError('Attachment request cancelled.'))
        future = asyncio.get_running_loop().create_future()
        def aborted(*_args):
            release(True)
            if not future.done():
                future.set_exception(abort_reason(signal))
        dispose = signal.add_listener('abort', aborted) if signal is not None else lambda: None
        def complete(done):
            dispose()
            release(False)
            if future.done():
                return
            if done.cancelled():
                future.cancel()
            elif done.exception() is not None:
                future.set_exception(compression_failure(done.exception()))
            else:
                future.set_result(done.result())
        self.task.add_done_callback(complete)
        try:
            return await future
        except asyncio.CancelledError:
            release(True)
            dispose()
            raise
