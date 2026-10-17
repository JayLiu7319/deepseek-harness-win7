"""rc3 canonical-log capture and feedback-only OpenTelemetry backend."""
import copy
import inspect
import time
import weakref
from types import SimpleNamespace

from dsh.core.session.current_session import CurrentSession
from dsh.cordis.utils import js_to_string
from dsh.session.telemetry import OpenTelemetrySessionBackend, LOG


_HANDOFF = weakref.WeakKeyDictionary()
DISABLED_FEEDBACK_WARNING = 'OpenTelemetry session upload is DISABLED; this feedback is not uploaded through OpenTelemetry'
NON_CANONICAL_EVENT_WARNING = 'session telemetry ignored an event absent from the canonical session log'


def is_feedback(session, event):
    if event['seq'] < session.inheritedEventCount:
        return False
    if event['type'] == 'feedback/record':
        return True
    return event['type'] in ('feedback/message-put', 'feedback/message-delete') and event['data']['sessionId'] == session.id


class SessionTelemetryCoordinator:
    def __init__(self, ctx, backend, options=None):
        self.ctx, self.backend, self.options, self.adopted = ctx, backend, options or {}, set()
        if self.options.get('capture', 'live') == 'live':
            ctx.on('session/created', self.adopt)
            ctx.on('session/disposed', self.disposed)
            ctx.on('session/event', lambda session, event: self.contain(lambda: self.capture_event(session, event)))
            ctx.on('session/flush', self.flush)
            ctx.on('agent/error', lambda value: self.contain(lambda: self.agent_error(value)))
            for session in ctx.get('sessions').list():
                self.adopt(session)
        ctx.effect(lambda: self.dispose, 'telemetry capture')

    def contain(self, callback):
        try:
            return callback()
        except Exception as error:
            self.ctx.logger.warn('telemetry: capture step failed: ' + str(error))

    def redact(self, record):
        return self.ctx.waterfall_sync('session-telemetry/record', record, lambda *_: record)

    def deliver(self, session, record, seq=None):
        self.backend.emit(self.redact(record))
        if seq is not None:
            _HANDOFF[session] = seq

    def capture_event(self, session, event):
        attributes = {'session.id': str(session.id), 'session.format_version': session.header.version,
                      'event.type': event['type'], 'event.seq': event['seq']}
        for field, key in (('cwd', 'session.cwd'), ('parentSession', 'session.parent_id')):
            value = getattr(session.header, field)
            if value is not None:
                attributes[key] = value
        if session.header.isSeeded:
            attributes['session.seed_length'] = session.inheritedEventCount
        data, kind = event['data'], event['type']
        error = kind == 'turn/end' and data['reason']['kind'] == 'error'
        if kind == 'tool/result':
            error = data['message']['content'][0].get('isError') is True
        self.deliver(session, dict(channel='ledger', time=event['time'], severity='error' if error else 'info',
                                  attributes=attributes, body=copy.deepcopy(data)), event['seq'])

    def captureSession(self, session, through=None):
        cursor = _HANDOFF.get(session, -1 if self.options.get('includeHistory') is True or session.firstLiveSeq == 0 else session.firstLiveSeq - 1)
        for event in session.snapshotEvents(cursor + 1):
            if through is not None and event['seq'] > through:
                break
            self.contain(lambda event=event: self.capture_event(session, event))

    def adopt(self, session):
        if session not in self.adopted:
            self.adopted.add(session)
            self.captureSession(session)

    def shutdown_record(self, session):
        return dict(channel='ops', time=int(time.time() * 1000), severity='info',
                    attributes={'telemetry.op': 'shutdown', 'session.id': str(session.id)}, body=dict(op='shutdown'))

    def disposed(self, session):
        if session in self.adopted:
            self.adopted.remove(session)
            self.contain(lambda: self.deliver(session, self.shutdown_record(session)))

    def flush(self, session):
        if session in self.adopted and callable(getattr(self.backend, 'flush', None)):
            self.contain(self.backend.flush)

    def agent_error(self, value):
        agent, error = value['agent'], value['error']
        name = getattr(error, 'name', 'TypeError' if isinstance(error, TypeError) else 'Error')
        detail = dict(name=name, message=str(error) if isinstance(error, Exception) else js_to_string(error))
        self.deliver(agent.session, dict(channel='ops', time=int(time.time() * 1000), severity='error',
            attributes={'telemetry.op': 'agent-error', 'session.id': str(agent.session.id), 'agent.id': agent.id,
                        'error.name': name, 'turn': value['turn'], 'step': value['step']}, body=detail))

    def dispose(self):
        # JS async cleanup emits before its first await. Keep that prefix
        # synchronous so same-fiber redaction rules still own shutdown records.
        for session in self.adopted:
            self.contain(lambda session=session: self.deliver(session, self.shutdown_record(session)))
        try:
            result = self.backend.shutdown()
        except Exception as error:
            self.ctx.logger.warn('telemetry: backend shutdown failed: ' + str(error))
            return
        async def finish():
            try:
                if inspect.isawaitable(result):
                    await result
            except Exception as error:
                self.ctx.logger.warn('telemetry: backend shutdown failed: ' + str(error))
        return finish()


class CurrentOpenTelemetrySessionBackend(OpenTelemetrySessionBackend):
    """Keep SDK transport ownership; authorize only newly submitted feedback."""
    app_version = '0.1.5-rc.3'
    instrumentation_version = '0.1.5-rc.3'
    def __init__(self, ctx, config=None):
        config = dict(config or {})
        if config.get('mode') is None:
            config['mode'] = 'FEEDBACK_ONLY'
        processor = dict(config.get('processor') or {})
        # JS has one number domain; Python's batch slicing needs int objects.
        for key in ('maxExportBatchSize', 'maxQueueSize'):
            value = processor.get(key)
            if type(value) is float and value.is_integer():
                processor[key] = int(value)
        config['processor'] = processor
        if config['mode'] not in ('FEEDBACK_ONLY', 'DISABLED'):
            raise ValueError('session-telemetry-otel: unsupported mode ' + repr(config['mode']))
        super().__init__(ctx, config)
        self.coordinator = None
        if self.mode != 'DISABLED':
            self.coordinator = SessionTelemetryCoordinator(ctx, SimpleNamespace(emit=self._export_record, shutdown=self.shutdown),
                dict(capture='on-demand', includeHistory=True))
            ctx.on('feedback/committed', self.committed)

    def emit(self, record):
        pass

    def event(self, session, event):
        if self.closed or not is_feedback(session, event):
            return
        if self.mode == 'DISABLED':
            LOG.warning(DISABLED_FEEDBACK_WARNING)
        elif session.eventAt(event['seq']) is not event:
            LOG.warning(NON_CANONICAL_EVENT_WARNING)
        else:
            self.coordinator.captureSession(session, event['seq'])

    def committed(self, inspection):
        snapshot = copy.deepcopy(inspection)
        events = snapshot['events']
        if not events:
            return
        committed = events[-1]
        session = CurrentSession.fromRestore(snapshot['meta']['id'], events, snapshot['meta'], snapshot['inheritedEventCount'], 'detached')
        if is_feedback(session, committed):
            self.coordinator.captureSession(session, committed['seq'])
