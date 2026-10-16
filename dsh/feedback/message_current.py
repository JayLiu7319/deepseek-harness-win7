"""Current message feedback: canonical log events and held cold write handles."""
import asyncio
import copy
import inspect
import time
import uuid

from dsh.cordis.schema import Schema as s
from dsh.cordis.text import trim_js
from dsh.core.session.json import deep_freeze, UNDEFINED
from dsh.core.session.current_surface import deriveEventMessage
from dsh.feedback.schema_current import validate_feedback
from dsh.typert.remote import Remote, TypertRemoteService


def success(value):
    return deep_freeze(dict(ok=True, value=value))


def rejected(error):
    return deep_freeze(dict(ok=False, error=error))


def current_items(session_id, events):
    items = {}
    for event in events:
        if event['type'] == 'feedback/message-put':
            data = event['data']
            validate_feedback(data, True)
            item = data['item']
            if data['sessionId'] == session_id:
                items[item['messageId']] = item
        elif event['type'] == 'feedback/message-delete':
            data = event['data']
            validate_feedback(data, False)
            if data['sessionId'] == session_id:
                items.pop(data['messageId'], None)
    return list(items.values())


def header_identity(header):
    if hasattr(header, 'to_dict'):
        header = header.to_dict()
    return [header.get(key) for key in ('id', 'createdAt', 'cwd')]


class CurrentMessageFeedback(TypertRemoteService):
    inject = ['sessionPersistence', 'sessions']
    Config = s.object(dict(maxNoteBytes=s.number().step(1).min(1).required()))

    def __init__(self, ctx, config):
        super().__init__(ctx, 'messageFeedback')
        maximum = config.get('maxNoteBytes')
        if type(maximum) not in (int, float) or not 1 <= maximum <= 9007199254740991 or maximum != int(maximum):
            raise TypeError('message-feedback: maxNoteBytes must be a positive safe integer')
        self.max_note_bytes = maximum
        self.operation_tails = {}
        self.mutation_admission_open = True
        ctx.effect(lambda: self.dispose, 'message-feedback.drain')

    async def dispose(self):
        self.mutation_admission_open = False
        await asyncio.gather(*list(self.operation_tails.values()))

    def enqueue(self, session_id, operation):
        async def run():
            if previous is not None:
                await previous
            return await operation()
        if not self.mutation_admission_open:
            future = asyncio.get_running_loop().create_future()
            future.set_exception(RuntimeError('message-feedback: service is disposing'))
            return future
        previous = self.operation_tails.get(session_id)
        task = asyncio.create_task(run())
        async def settle():
            try:
                await task
            except BaseException:
                pass
        tail = asyncio.create_task(settle())
        self.operation_tails[session_id] = tail
        def finished(_):
            if self.operation_tails.get(session_id) is tail:
                self.operation_tails.pop(session_id, None)
        tail.add_done_callback(finished)
        return asyncio.shield(task)

    @Remote('list')
    def list(self, request):
        return self.enqueue(request['sessionId'], lambda: self.with_session(request['sessionId'], False,
            lambda events, append: success(dict(items=copy.deepcopy(current_items(request['sessionId'], events))))))

    @Remote('put')
    def put(self, request):
        note = request.get('note', UNDEFINED)
        failure = None
        if note is not UNDEFINED:
            if not trim_js(note):
                failure = dict(code='note-blank')
            elif len(note.encode('utf-8')) > self.max_note_bytes:
                failure = dict(code='note-too-large', maxBytes=self.max_note_bytes, actualBytes=len(note.encode('utf-8')))
        if failure is not None:
            future = asyncio.get_running_loop().create_future()
            future.set_result(rejected(failure))
            return future
        async def operation(events, append):
            items = current_items(request['sessionId'], events)
            if not any(event['type'] == 'assistant/message' and event.get('surfaceOp') == 'append'
                       and (deriveEventMessage(event) or {}).get('id') == request['messageId'] for event in events):
                return rejected(dict(code='target-not-found', sessionId=request['sessionId'], messageId=request['messageId']))
            existing = next((item for item in items if item['messageId'] == request['messageId']), None)
            if request['ifVersion'] != (existing['version'] if existing else None):
                return self.version_conflict(existing)
            desired = {key: request[key] for key in ('rating', 'category') if key in request}
            if note is not UNDEFINED:
                desired['note'] = note
            if existing is not None and all(existing.get(key, UNDEFINED) == desired.get(key, UNDEFINED) for key in ('rating', 'note', 'category')):
                await append()
                return success(copy.deepcopy(existing))
            now = int(time.time() * 1000)
            item = dict(messageId=request['messageId'], **desired, version=str(uuid.uuid4()),
                        createdAt=existing['createdAt'] if existing else now,
                        updatedAt=max(now, existing['updatedAt']) if existing else now)
            await append(dict(type='feedback/message-put', data=dict(sessionId=request['sessionId'], item=item)))
            return success(item)
        return self.enqueue(request['sessionId'], lambda: self.with_session(request['sessionId'], True, operation))

    @Remote('delete')
    def delete(self, request):
        async def operation(events, append):
            existing = next((item for item in current_items(request['sessionId'], events) if item['messageId'] == request['messageId']), None)
            if existing is not None:
                if request['ifVersion'] != existing['version']:
                    return self.version_conflict(existing)
                await append(dict(type='feedback/message-delete', data=dict(sessionId=request['sessionId'], messageId=request['messageId'])))
            else:
                await append()
            return success(dict(absent=True))
        return self.enqueue(request['sessionId'], lambda: self.with_session(request['sessionId'], True, operation))

    @staticmethod
    def version_conflict(existing):
        return rejected(dict(code='version-conflict', current=copy.deepcopy(existing)))

    async def with_session(self, session_id, write, operation):
        sessions, persistence = self.ctx.get('sessions'), self.ctx.get('sessionPersistence')
        if sessions.get(session_id) is None and await persistence.stat(session_id) is None and sessions.get(session_id) is None:
            return rejected(dict(code='session-not-found', sessionId=session_id))
        live = sessions.get(session_id)
        if live is not None:
            async def append(event=None):
                if event is not None:
                    live.append(event['type'], event['data'])
                events = live.snapshotEvents()
                last = events[-1] if events else None
                if not await sessions.flush(live):
                    raise RuntimeError("message-feedback: no durability listener participated for live session '{}'".format(session_id))
                handle = await persistence.open(session_id, 'read')
                try:
                    stored = (await handle.read(last['seq'] if last else 0, 1))['events']
                    if header_identity(handle.header) != header_identity(live.header) or last is not None and (not stored or stored[0] != last):
                        raise RuntimeError("message-feedback: feedback prefix is not durable for live session '{}'".format(session_id))
                finally:
                    await handle.close()
            result = operation(live.snapshotEvents(), append)
            return await result if inspect.isawaitable(result) else result
        handle = await persistence.open(session_id, 'write' if write else 'read')
        try:
            events = (await handle.read())['events']
            async def append(event=None):
                entry = dict(event, seq=len(events), time=int(time.time() * 1000)) if event is not None else None
                if entry is not None:
                    await handle.append([entry])
                await handle.flush()
                if entry is not None:
                    try:
                        await self.ctx.parallel('feedback/committed', dict(meta=handle.header,
                            inheritedEventCount=handle.inheritedEventCount, events=list(events) + [entry]))
                    except Exception as error:
                        self.ctx.logger.warn('message-feedback: committed feedback observer failed', error)
            result = operation(events, append)
            return await result if inspect.isawaitable(result) else result
        finally:
            await handle.close()
