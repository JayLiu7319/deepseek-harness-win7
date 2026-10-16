"""v3 JSONL handles: single mutation chain, durable live drain, owned teardown.

Public mutations snapshot on invocation, before entering the queue. Observer
cancellation never cancels an already queued write or a shared close/drain.
"""
import asyncio
import copy
import inspect

from dsh.core.session.current import safe
from dsh.session.format_v2_to_v3.payload import display
from dsh.session.preparations import throw_aborted
from dsh.session.persistence import (
    SessionAlreadyExistsError, SessionAlreadyOwnedError, SessionHandleClosedError,
    SessionPersistenceNotFoundError, SessionReadOnlyError)
from dsh.session.storage_contract import materializeAppendBatch, assertContiguous, field

LIVE_WRITE_BATCH_MAX_DELAY_MS = 200


class StorageAggregateError(Exception):
    name = 'AggregateError'

    def __init__(self, errors, message):
        super().__init__(message)
        self.errors = errors


async def resolved(value):
    return await value if inspect.isawaitable(value) else value


def failed(error):
    future = asyncio.get_running_loop().create_future()
    future.set_exception(error)
    return future


def signal_of(options):
    return field(options, 'signal', None)


class JsonlSessionHandle:
    def __init__(self, storage, session_id, header, access, state, lease=None):
        self.storage, self.id, self.header, self.access = storage, session_id, header, access
        self.state, self.lease = state, lease
        self._chain = asyncio.get_running_loop().create_future()
        self._chain.set_result(None)
        self._closing = None
        self.observedLength = 0
        self.buffered = []
        self.batchTimer, self.draining = None, None
        self.drainPaused = False

    @property
    def inheritedEventCount(self):
        return self.state['inheritedEventCount']

    def _assert_open(self, operation):
        if self._closing is not None:
            raise SessionHandleClosedError(self.id, operation)

    def _enqueue(self, operation):
        previous = self._chain
        async def run():
            await previous
            return await operation()
        task = asyncio.create_task(run())
        async def settled():
            try:
                await task
            except BaseException:
                pass
        self._chain = asyncio.create_task(settled())
        return asyncio.shield(task)

    def _run(self, name, operation):
        try:
            self._assert_open(name)
        except Exception as error:
            return failed(error)
        async def guarded():
            self._assert_open(name)
            return await operation()
        return self._enqueue(guarded)

    def read(self, offset=0, length=9007199254740991, options=None):
        try:
            self._assert_open('read')
            for name, value in (('offset', offset), ('length', length)):
                if not safe(value, True):
                    raise TypeError('read %s must be a non-negative safe integer, got %s' % (name, display(value)))
            throw_aborted(signal_of(options))
        except Exception as error:
            return failed(error)
        return asyncio.create_task(self._read(int(offset), int(length), signal_of(options)))

    async def _read(self, offset, length, signal):
        primed = self.state.get('primed')
        if primed is not None:
            if self.access == 'write':
                return self._read_primed(primed, offset, length)
            path = await resolved(self.storage.resolveCurrentLog(self.id, signal))
            if path is None:
                return self._read_primed(primed, offset, length)
            self.state.pop('primed', None)
            return await self._read_current(path, offset, length, signal)
        if self.access == 'write' and not self.state['materialized']:
            return dict(eventState='detached', events=[])
        path = await resolved(self.storage.resolveCurrentLog(self.id, signal))
        if path is not None:
            return await self._read_current(path, offset, length, signal)
        if self.storage.hasPendingSession(self.id):
            return dict(eventState='detached', events=[])
        raise SessionPersistenceNotFoundError(self.id)

    def _read_primed(self, source, offset, length):
        self.observedLength = max(self.observedLength, len(source['events']))
        return dict(eventState=source['eventState'], events=source['events'][offset:offset+length])

    async def _read_current(self, path, offset, length, signal):
        source = await resolved(self.storage.readStoredLog(path, self.id, signal))
        size = len(source['events'])
        if size < self.observedLength:
            raise ValueError('session "%s": stored log shrank below a previously observed prefix (%s < %s)' % (self.id, size, self.observedLength))
        self.observedLength = size
        return dict(eventState=source['eventState'], events=source['events'][offset:offset+length])

    def append(self, events, options=None):
        try:
            self._assert_open('append')
            batch = materializeAppendBatch(events)
        except Exception as error:
            return failed(error)
        async def write():
            throw_aborted(signal_of(options))
            await self._persist_contiguous(batch)
        return self._run('append', write)

    def flush(self, options=None):
        async def barrier():
            throw_aborted(signal_of(options))
            if self.access != 'write':
                raise SessionReadOnlyError(self.id, 'flush')
            if self.state['materialized']:
                return
            await self._ensure_lease()
            await resolved(self.storage.persistHeader(self.header, self.state['inheritedEventCount']))
            self.state['materialized'] = True
        return self._run('flush', barrier)

    def close(self):
        if self._closing is None:
            self._closing = asyncio.create_task(self._close())
        return asyncio.shield(self._closing)

    async def _close(self):
        errors = []
        while True:
            try:
                await self.drainLive()
            except Exception as error:
                errors.append(error)
                break
            await self._chain
            if not self.buffered:
                break
        await self._chain
        try:
            if self.lease is not None:
                await resolved(self.lease.release())
        except Exception as error:
            errors.append(error)
        self.storage.releaseHandle(self, self.state['materialized'])
        if len(errors) > 1:
            raise StorageAggregateError(errors, 'session "%s": close failed to drain and to release its write lock' % self.id)
        if errors:
            raise errors[0]

    async def __aenter__(self):
        self._assert_open('read')
        return self

    async def __aexit__(self, *args):
        await self.close()

    def enqueueLive(self, event, reportBackgroundFailure):
        self.buffered.append(copy.deepcopy(event))
        if self.batchTimer is not None or self.drainPaused:
            return
        def deadline():
            self.batchTimer = None
            future = self.drainLive()
            def report(result):
                try:
                    result.result()
                except Exception as error:
                    reportBackgroundFailure(error)
            future.add_done_callback(report)
        self.batchTimer = asyncio.get_running_loop().call_later(LIVE_WRITE_BATCH_MAX_DELAY_MS / 1000, deadline)

    def drainLive(self):
        if self.draining is None:
            if self.batchTimer is not None:
                self.batchTimer.cancel()
                self.batchTimer = None
            self.drainPaused = False
            self.draining = asyncio.create_task(self._drain_buffered())
        return asyncio.shield(self.draining)

    async def _drain_buffered(self):
        try:
            while self.buffered:
                async def write():
                    batch, self.buffered = self.buffered, []
                    try:
                        await self._persist_contiguous(materializeAppendBatch(batch))
                    except Exception:
                        self.buffered = batch + self.buffered
                        self.drainPaused = True
                        raise
                await self._enqueue(write)
        finally:
            self.draining = None

    async def _persist_contiguous(self, batch):
        if self.access != 'write':
            raise SessionReadOnlyError(self.id, 'append')
        if not batch:
            return
        await self._ensure_lease()
        assertContiguous(self.id, batch, self.state['cursor'])
        if self.state.get('tornTruncateTo') is not None:
            await resolved(self.storage.truncateTornTail(self.header, self.state['tornTruncateTo']))
            self.state.pop('tornTruncateTo', None)
        if self.state.get('recoveredTail') is not None:
            if self.state['recoveredTail']:
                await resolved(self.storage.persistBatch(self.header, self.state['recoveredTail'], self.state['materialized'], self.state['inheritedEventCount']))
            self.state.pop('recoveredTail', None)
        await resolved(self.storage.persistBatch(self.header, batch, self.state['materialized'], self.state['inheritedEventCount']))
        self.state['materialized'] = True
        self.state['cursor'] += len(batch)
        self.state.pop('primed', None)
        self.observedLength = self.state['cursor']

    async def _ensure_lease(self):
        if self.lease is None:
            self.lease = await resolved(self.storage.acquireWriteLease(self.header))


class JsonlBackendTracker:
    def __init__(self, name):
        self.name = name
        # Dict preserves Source Set insertion order for teardown and failure order.
        self.openHandles, self.writers, self.pending = {}, {}, {}
        self.counter = 0

    def registerCreated(self, header, inheritedEventCount):
        session_id = field(header, 'id')
        if session_id in self.writers:
            raise SessionAlreadyExistsError(session_id)
        self.writers[session_id] = None
        self.counter += 1
        self.pending[session_id] = dict(header=header, revision='memory:%s:%s' % (self.name, self.counter), inheritedEventCount=inheritedEventCount)

    def claimWrite(self, session_id):
        if session_id in self.writers:
            raise SessionAlreadyOwnedError(session_id)
        self.writers[session_id] = None

    def releaseClaim(self, session_id):
        self.writers.pop(session_id, None)

    def pendingOf(self, session_id):
        return self.pending.get(session_id)

    def hasPending(self, session_id):
        return session_id in self.pending

    def pendingEntries(self):
        return iter(self.pending.items())

    def materialized(self, session_id):
        self.pending.pop(session_id, None)

    def adopt(self, handle):
        self.openHandles[handle] = None
        if handle.access == 'write':
            self.writers[handle.id] = handle
        return handle

    def release(self, handle, materialized):
        self.openHandles.pop(handle, None)
        if handle.access == 'write':
            self.writers.pop(handle.id, None)
            if not materialized:
                self.pending.pop(handle.id, None)

    async def flushAll(self):
        errors = []
        for writer in list(self.writers.values()):
            if writer is None:
                continue
            try:
                await writer.drainLive()
                await writer.flush()
            except SessionHandleClosedError:
                pass
            except Exception as error:
                errors.append(error)
        if errors:
            raise StorageAggregateError(errors, '%s flush failed' % self.name)

    async def dispose(self):
        errors = []
        for handle in list(self.openHandles):
            try:
                await handle.close()
            except Exception as error:
                errors.append(error)
        if errors:
            raise StorageAggregateError(errors, '%s dispose failed' % self.name)

    def install(self, ctx):
        def warning(label, session_id, error):
            ctx.logger.warn('session-persistence: %s for session "%s" failed%s: %s' % (
                label, session_id, ' (buffered events retained)' if label == 'background write' else '', error))
        def on_event(session, event):
            writer = self.writers.get(session.id)
            if writer is not None:
                writer.enqueueLive(event, lambda error: warning('background write', session.id, error))
        async def on_flush(session):
            writer = self.writers.get(session.id)
            if writer is not None:
                await writer.drainLive()
                await writer.flush()
        def on_disposed(session):
            writer = self.writers.get(session.id)
            if writer is not None:
                def report(result):
                    try:
                        result.result()
                    except Exception as error:
                        warning('final drain', session.id, error)
                writer.close().add_done_callback(report)
        ctx.on('session/event', on_event)
        ctx.on('session/flush', on_flush)
        ctx.on('session/disposed', on_disposed)
        ctx.effect(lambda: self.dispose, '%s open handles' % self.name)
