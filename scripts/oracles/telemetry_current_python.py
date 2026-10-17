"""Current capture coordinator against a recording sink and exact Session identity."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import patch

from dsh.cordis.context import Context
from dsh.session.telemetry_current import SessionTelemetryCoordinator


def execute(test):
    async def run():
        ctx = Context()
        events = copy.deepcopy(test['events'])
        # SimpleNamespace has no weak-reference identity; Session actors need
        # the same weak ownership as real Session objects.
        class Session: pass
        session = Session()
        session.id, session.seq, session.events = 'telemetry', len(events), events
        session.header = SimpleNamespace(version=3, cwd='/workspace', parentSession='parent' if test.get('seeded') else None, isSeeded=test.get('seeded', False))
        session.inheritedEventCount = test.get('cut', 0)
        session.firstLiveSeq = test.get('firstLive', 0)
        session.snapshotEvents = lambda offset=0: events[int(offset):]
        ctx.set_service('sessions', SimpleNamespace(list=lambda: [session]))
        records, calls = [], []
        def emit(record):
            if record['attributes'].get('event.seq') == test.get('rejectSeq', -99):
                raise RuntimeError('sink rejected')
            records.append(copy.deepcopy(record));calls.append('emit')
        def flush(): calls.append('flush')
        async def shutdown(): calls.append('shutdown')
        def policy(record, next):
            if record['attributes'].get('event.seq') == test.get('redactRejectSeq', -99):
                raise RuntimeError('policy rejected')
            if test.get('redact'):
                record['body'] = dict(redacted=True)
            return next()
        ctx.on('session-telemetry/record', policy)
        sink = SimpleNamespace(emit=emit, flush=flush, shutdown=shutdown)
        holder = []
        async def mount():
            if test.get('rootScope'):
                return SessionTelemetryCoordinator(ctx, sink, test['options'])
            def setup(child):
                holder.append(SessionTelemetryCoordinator(child, sink, test['options']))
            await ctx.plugin(setup)
            return holder[-1]
        coordinator = await mount()
        for action in test['actions']:
            if action == 'capture': coordinator.captureSession(session, test.get('through'))
            elif action == 'reload': coordinator = await mount()
            elif action == 'flush': ctx.emit('session/flush', session)
            elif action == 'disposed': ctx.emit('session/disposed', session)
            elif action == 'notify':
                for event in events: ctx.emit('session/event', session, event)
        await ctx.fiber.dispose()
        return dict(records=records, calls=calls, events=events)
    with patch('dsh.session.telemetry_current.time.time', return_value=1):
        return asyncio.run(run())
