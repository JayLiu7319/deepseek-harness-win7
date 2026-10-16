"""Current logical history pages and gap-free durable/live Assistant following."""
import asyncio
import math
from collections import deque

from dsh.api.session_assistant_stream_current import SessionAssistantStreamAccumulator
from dsh.cordis.utils import js_to_string
from dsh.session.session_query import SessionQueryError
from dsh.typert.remote import RemoteError


def safe_integer(value):
    return type(value) in (int, float) and abs(value) <= 9007199254740991 and math.isfinite(value) and int(value) == value


def negative_zero(value):
    return value == 0 and math.copysign(1, value) < 0


def validate_request(request, page=False):
    if page:
        through = request.get('throughSeq')
        if not safe_integer(through) or through < -1 or negative_zero(through):
            raise RemoteError('gateway/bad-request', 'throughSeq must be an integer greater than or equal to -1', {})
        if 'beforeSeq' in request:
            before = request['beforeSeq']
            if not safe_integer(before) or before < 0 or negative_zero(before):
                raise RemoteError('gateway/bad-request', 'beforeSeq must be a non-negative safe integer', {})
    if 'maxMessages' in request and (not safe_integer(request['maxMessages']) or request['maxMessages'] <= 0):
        raise RemoteError('gateway/bad-request', 'maxMessages must be a positive safe integer', {})


def page_records(events):
    return [dict(type='event', event=event) for event in events]


def paginate(events, before=None, maximum=50, through=None):
    through = events[-1]['seq'] if through is None and events else -1 if through is None else through
    end = int(min(through + 1, before if before is not None else through + 1))
    count, cut = 0, 0
    for index in range(end - 1, -1, -1):
        event = events[index]
        if event['type'] not in ('user/message', 'assistant/message') or event.get('surfaceOp') != 'append':
            continue
        count += 1
        if count >= maximum:
            cut = int(min([event['seq']] + list(event.get('sourceEventSeqs', []))))
            break
    return events[cut:end], cut > 0


def address_id(address):
    return address['sessionId'] if address['kind'] == 'session' else address['childSessionId']


def not_found(address):
    if address['kind'] == 'session':
        return RemoteError('session/not-found', 'session "{}" not found'.format(address['sessionId']), dict(sessionId=address['sessionId']))
    return RemoteError('subagent/not-found', 'subagent is unavailable', {key: address[key] for key in ('parentSessionId', 'childSessionId')})


def validate_address(address, header, cut, projections):
    if address['kind'] == 'session':
        if header.origin == 'subagent':
            raise RemoteError('session/agent-busy', 'subagent Sessions require their durable parent address', dict(reason='use subagent delivery for this child session'))
        return
    sid = address['childSessionId']
    if header.origin != 'subagent' or header.parentSession != address['parentSessionId']:
        raise RemoteError('subagent/unauthorized', 'subagent does not belong to the supplied parent', dict(childSessionId=sid))
    values = (projections or {}).get('values', {})
    details = dict(parentSessionId=address['parentSessionId'], childSessionId=sid)
    if 'subagent' in values and values['subagent'] is None:
        raise RemoteError('subagent/catalog-diagnostic', 'subagent descriptor is corrupt', dict(details, reason='corrupt'))
    identity = values.get('subagent')
    if identity is None or identity['seq'] < cut:
        raise RemoteError('subagent/catalog-diagnostic', 'subagent descriptor is unavailable', dict(details, reason='unsupported'))
    if identity['mode'] != address['mode']:
        raise RemoteError('subagent/unauthorized', 'subagent mode does not match the supplied address', dict(childSessionId=sid))


class CurrentSessionHistory:
    def __init__(self, ctx, promote):
        self.ctx, self.promote, self.followers, self.assistant_streams = ctx, promote, set(), {}
        def assistant(payload):
            agent, frame = payload['agent'], payload['frame']
            if agent.session.id not in self.assistant_streams:
                self.assistant_streams[agent.session.id] = SessionAssistantStreamAccumulator()
            self.assistant_streams[agent.session.id].accept(frame, agent.session.seq - 1)
        ctx.on('agent/assistant-stream', assistant, global_listener=True)
        ctx.on('agent/disposed', lambda payload: self.assistant_streams.pop(payload['agent'].session.id, None), global_listener=True)
        ctx.effect(lambda: self.close)

    def close(self):
        for close in list(self.followers):
            close()
        self.followers.clear()

    async def source(self, address, signal, projections):
        sid = address_id(address)
        try:
            observed = await self.ctx.get('sessionQuery').observeSession(sid, dict(signal=signal, projectionMode='all' if projections or address['kind'] == 'subagent' else 'none'))
        except SessionQueryError as error:
            if error.code == 'SESSION_QUERY_SESSION_NOT_FOUND':
                raise not_found(address) from None
            raise
        try:
            if observed.header.cwd is None:
                raise not_found(address)
            validate_address(address, observed.header, observed.inheritedEventCount, observed.projections)
            return observed
        except BaseException:
            observed.dispose()
            raise

    async def page(self, request, signal):
        validate_request(request, True)
        source = await self.source(request['address'], signal, False)
        try:
            signal.throwIfAborted()
            through = int(request['throughSeq'])
            cursor = source.events[-1]['seq'] if source.events else -1
            if through > cursor:
                raise RemoteError('gateway/bad-request', 'session page through seq {} is past cursor {}'.format(through, cursor), {})
            if through >= 0 and (through >= len(source.events) or source.events[through]['seq'] != through):
                raise RemoteError('gateway/internal', 'session log does not contain through seq {}'.format(through), {})
            events, more = paginate(source.events, int(request['beforeSeq']) if 'beforeSeq' in request else None,
                request.get('maxMessages', 50), through)
            return dict(records=page_records(events), hasMore=more)
        finally:
            source.dispose()

    async def follow(self, request, signal):
        validate_request(request)
        address = request['address']
        sid, buffered, wake = address_id(address), deque(), asyncio.Event()
        snapshot_cursor, ordinal, closed = None, 0, False
        def close():
            nonlocal closed
            closed = True
            wake.set()
        self.followers.add(close)
        def event(session, value):
            if session.id == sid:
                buffered.append(dict(type='event', event=value)); wake.set()
        def created(session):
            if session.id != sid:
                return
            suffix = session.snapshotEvents(session.firstLiveSeq if snapshot_cursor is None else snapshot_cursor + 1)
            for value in reversed(suffix):
                buffered.appendleft(dict(type='event', event=value))
            wake.set()
        def assistant(payload):
            nonlocal ordinal
            agent, frame = payload['agent'], payload['frame']
            if agent.session.id != sid:
                return
            ordinal += 1
            wire = dict(frame, startedAfterSeq=agent.session.seq - 1) if frame['type'] == 'start' else frame
            buffered.append(dict(type='assistant-stream', frame=wire, ordinal=ordinal)); wake.set()
        remove_event = self.ctx.on('session/event', event, global_listener=True)
        remove_created = self.ctx.on('session/created', created, global_listener=True)
        remove_assistant = self.ctx.on('agent/assistant-stream', assistant, global_listener=True) if request.get('assistantStream') is True else lambda: None
        remove_abort = signal.add_listener('abort', lambda *_: wake.set())
        source = None
        try:
            source = await self.source(address, signal, True)
            signal.throwIfAborted()
            cursor = source.cursor
            snapshot_cursor = cursor
            events, more = paginate(source.events, maximum=request.get('maxMessages', 50))
            baseline = None
            if request.get('assistantStream') is True:
                accumulator = self.assistant_streams.get(sid)
                baseline = accumulator.snapshot() if accumulator is not None else dict(revision=0)
            ordinal_cut = ordinal
            yield dict(type='snapshot', header=source.header.to_dict(), cursor=cursor, records=page_records(events), hasMore=more,
                projections=source.projections if source.projections is not None else dict(asOfSeq=cursor, values={}),
                **(dict(assistantStream=baseline) if baseline is not None else {}))
            if address['kind'] == 'session' and source.source == 'prepared':
                retained = source.retain()
                try:
                    self.promote(retained)
                except BaseException:
                    retained.dispose()
                    raise
            next_offset = cursor + 1
            while not closed and not signal.aborted:
                if not buffered:
                    wake.clear()
                    await wake.wait()
                    continue
                item = buffered.popleft()
                if item['type'] == 'assistant-stream':
                    if item['ordinal'] > ordinal_cut:
                        yield dict(type='assistant-stream', frame=item['frame'])
                    continue
                if item['event']['seq'] < next_offset:
                    continue
                if item['event']['seq'] != next_offset:
                    raise RemoteError('gateway/internal', 'session event stream skipped seq {}'.format(js_to_string(next_offset)), {})
                next_offset += 1
                yield item
        finally:
            if source is not None:
                source.dispose()
            self.followers.discard(close)
            remove_abort(); remove_created(); remove_event(); remove_assistant()
