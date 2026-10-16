"""Released v1 chunks become v2 embedded attempts, with audited coordinate remapping."""
from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import _js_strict_equal
from dsh.llm.assistant_stream import AssistantStreamAccumulator, integer
from dsh.session.format import SessionFormatUnsupportedMigrationError, defineSessionFormatMigration, sessionFormatCount
from dsh.session.format.chain import member, call
from dsh.session.format_v0_to_v1 import (RELEASED_V0_EVENT_DISPOSITIONS, assertReleasedEventPayload,
    assertReleasedV1Header, isReleasedAssistantChunkRun)
from dsh.session.format_v0_to_v1.payload import compact
from .codec import assertReleasedV2Header


def refusal(message):
    return SessionFormatUnsupportedMigrationError(message)


def group(turn, step):
    return dict(turn=turn, step=step, spans=[], stream=[], chunkCount=0, terminal=False)


def append_stream(target, source, last_time, owned=True):
    previous = target['stream'][-1] if target['stream'] else None
    def append():
        value = source if owned or source['type'] == 'chunk' else dict(source,
            dt=list(source['dt']), **{('args' if source['type'] == 'tool-call-chunks' else 'texts'): list(source['args' if source['type'] == 'tool-call-chunks' else 'texts'])})
        target['stream'].append(dict(record=value, lastTime=last_time))
    if previous is None or source['type'] == 'chunk' or previous['record']['type'] != source['type']:
        append()
        return
    gap = source['time0'] - previous['lastTime']
    record = previous['record']
    if record['index'] != source['index'] or not integer(gap):
        append()
        return
    tool = source['type'] == 'tool-call-chunks'
    if tool and (record['id'] != source['id'] or record.get('name', UNDEFINED) != source.get('name', UNDEFINED)):
        append()
        return
    record['dt'].extend([gap] + list(source['dt']))
    key = 'args' if tool else 'texts'
    record[key].extend(source[key])
    previous['lastTime'] = last_time


def flush_accumulator(target):
    accumulator = target.pop('accumulator', None)
    if accumulator is None:
        return
    for value in accumulator.snapshot():
        last = value['time'] if value['type'] == 'chunk' else value['time0'] + sum(value['dt'])
        append_stream(target, value, last, False)


def stream_of(target):
    flush_accumulator(target)
    return [entry['record'] for entry in target['stream']]


def record_span(target, first, count, time):
    previous = target['spans'][-1] if target['spans'] else None
    if previous is not None and previous['firstSeq'] + previous['eventCount'] == first:
        previous['eventCount'] += count
    else:
        target['spans'].append(dict(firstSeq=first, eventCount=count))
    target['chunkCount'] += count
    target['lastChunkSeq'] = first + count - 1
    target['lastChunkTime'] = time


def matches_sources(target, sources):
    if len(sources) != target['chunkCount']:
        return False
    index = 0
    for span in target['spans']:
        for offset in range(span['eventCount']):
            if not _js_strict_equal(sources[index], span['firstSeq'] + offset):
                return False
            index += 1
    return True


def message_event(source, target):
    event = {key: value for key, value in source.items() if key != 'sourceEventSeqs'}
    return dict(event, data=dict(source['data'], stream=stream_of(target)))


class ReleasedV1ToV2Stage:
    def __init__(self, source):
        self.header = member(source, 'sourceHeader')
        assertReleasedV1Header(self.header)
        self.decoded = member(source, 'sourceKind') == 'decoded'
        self.source_cut = sessionFormatCount(member(source, 'sourceInheritedEventCount'), 'format v1 inherited event count')
        self.mapping = {}
        self.open_turn, self.open_step, self.previous = None, None, None
        self.pending = None
        self.target_seq = 0
        self.target_cut = UNDEFINED if self.header['isSeeded'] else 0
        self.last_time = self.header['createdAt']

    def transformEvent(self, event, context):
        kind, seq = event['type'], event['seq']
        if self.decoded and kind != 'assistant/chunk' and kind in RELEASED_V0_EVENT_DISPOSITIONS:
            assertReleasedEventPayload(event, 1)
        self.transform(event, context)

    def transform(self, event, context):
        kind, seq = event['type'], event['seq']
        if kind == 'assistant/chunk':
            required = ['type', 'seq', 'time', 'data']
            allowed = required + ['ignorable', 'sourceEventSeqs', 'surfaceOp']
            extra = next((key for key in event if key not in allowed), None)
            if extra is not None:
                raise refusal('assistant/chunk %s has unexpected member %s' % (seq, extra))
            missing = next((key for key in required if key not in event), None)
            if missing is not None:
                raise refusal('assistant/chunk %s lacks required member %s' % (seq, missing))
            if event.get('ignorable', UNDEFINED) is not UNDEFINED and event['ignorable'] is not True:
                raise refusal('assistant/chunk %s ignorable must be true when present' % seq)
        if kind not in RELEASED_V0_EVENT_DISPOSITIONS:
            raise refusal('format v1 contains unknown event type %s at seq %s' % (compact(kind), seq))
        data = event['data']
        interrupted = None
        if (kind == 'turn/start' and self.open_turn is not None and self.open_step is None
                and data['turn'] == self.open_turn + 1 and self.previous is not None and self.previous['type'] == 'agent/inbox/spliced'):
            splice = self.previous['data']
            if splice.get('target') == 'next-turn' and isinstance(splice.get('inserted'), list) and splice['inserted']:
                interrupted = dict(type='turn/end', seq=seq, time=event['time'], data=dict(turn=self.open_turn, reason=dict(kind='interrupted')))
        if kind == 'turn/start' and self.open_turn is not None and interrupted is None:
            raise refusal('turn/start %s does not close the prior turn' % compact(data['turn']))
        if kind == 'session-log-deepseek/delivery-accepted':
            inherited = self.header.get('parentSession', UNDEFINED) is not UNDEFINED and seq < self.source_cut
            if _js_strict_equal(data.get('sessionFormatVersion', UNDEFINED), 1) and not inherited and data['sessionId'] != self.header['id']:
                raise refusal('current-generation delivery marker names the wrong Session')
        if kind == 'turn/start':
            self.open_turn, self.open_step = data['turn'], None
        elif kind == 'turn/end':
            self.open_turn, self.open_step = None, None
        elif kind == 'step/start':
            self.open_step = data['step']
        elif kind == 'step/end':
            self.open_step = None
        self.previous = event
        self.last_time = event['time']
        if interrupted is not None:
            self.finish_attempt(context)
            self.emit_generated(seq, interrupted, context)
        if kind == 'user/message' and data['source'].get('kind') == 'goal' and data['source'].get('change', UNDEFINED) is not UNDEFINED:
            change = dict(type='goal/change', seq=seq, time=event['time'], data=data['source']['change'])
            message = dict(event, data=dict(data, source=dict(kind='plugin', plugin='goal')))
            self.emit_generated(seq, change, context)
            self.emit_source(message, context)
        elif kind == 'assistant/chunk':
            self.transform_chunk(event, context)
        elif kind == 'assistant/message':
            self.transform_message(event, context)
        elif kind in ('turn/end', 'step/end', 'llm/retry', 'llm/retry-started'):
            self.finish_attempt(context)
            self.emit_source(event, context)
        elif self.pending is not None:
            self.pending['afterLastChunk'].append(event)
        else:
            self.emit_source(event, context)

    def transformRun(self, run, context):
        if not isReleasedAssistantChunkRun(run):
            for event in call(run, 'expand'):
                # The upstream generic-run path shares the transformed-event
                # normalizer, even for a decoded-source stage.
                self.transform(event, context)
            return
        self.previous = None
        self.last_time = run['lastTime']
        self.prepare_group(run['turn'], run['step'], context)
        target = self.pending['group']
        if (run['firstSeq'] < self.source_cut) != (run['lastSeq'] < self.source_cut):
            raise refusal('inherited Session cut %s splits one Assistant attempt' % self.source_cut)
        flush_accumulator(target)
        append_stream(target, run['stream'], run['lastTime'])
        record_span(target, run['firstSeq'], run['eventCount'], run['lastTime'])

    def finish(self, context):
        self.finish_attempt(context)
        if self.header['isSeeded'] and self.target_cut is UNDEFINED:
            self.target_cut = self.target_seq
            call(context, 'emitEvent', dict(type='session/end-seed', seq=self.target_seq, time=self.last_time, data=dict(inherited=True)))
            self.target_seq += 1
        return self.target_cut

    def prepare_group(self, turn, step, context):
        if self.pending is not None:
            target = self.pending['group']
            if target['terminal'] or target['turn'] != turn or target['step'] != step:
                self.finish_attempt(context)
            else:
                self.flush_buffered(self.pending, context)
        if self.pending is None:
            self.pending = dict(group=group(turn, step), afterLastChunk=[])

    def assert_cut(self, target, seq):
        first = target['spans'][0]['firstSeq'] if target['spans'] else seq
        if (first < self.source_cut) != (seq < self.source_cut):
            raise refusal('inherited Session cut %s splits one Assistant attempt' % self.source_cut)

    def transform_chunk(self, event, context):
        data = event['data']
        self.prepare_group(data['turn'], data['step'], context)
        target = self.pending['group']
        self.assert_cut(target, event['seq'])
        if 'accumulator' not in target:
            target['accumulator'] = AssistantStreamAccumulator()
        target['accumulator'].push(dict(time=event['time'], chunk=data['chunk']))
        record_span(target, event['seq'], 1, event['time'])
        if data['chunk'].get('type') == 'finish':
            target['terminal'] = True

    def transform_message(self, event, context):
        data, seq = event['data'], event['seq']
        turn, step = data['turn'], data['step']
        sources = event.get('sourceEventSeqs', UNDEFINED)
        pending = self.pending
        if pending is not None and (pending['group']['turn'] != turn or pending['group']['step'] != step):
            self.finish_attempt(context)
            self.emit_source(message_event(event, group(turn, step)), context)
        elif not isinstance(sources, list):
            if pending is not None:
                raise refusal('assistant/message %s does not cite its complete v1 chunk attempt' % seq)
            self.emit_source(message_event(event, group(turn, step)), context)
        elif not sources:
            self.finish_attempt(context)
            self.emit_source(message_event(event, group(turn, step)), context)
        else:
            if pending is None or not matches_sources(pending['group'], sources):
                raise refusal('assistant/message %s chunk provenance is not one complete ordered attempt' % seq)
            target = pending['group']
            self.assert_cut(target, seq)
            target['terminal'] = True
            self.flush_buffered(pending, context)
            self.emit_source(message_event(event, target), context)
            self.pending = None

    def finish_attempt(self, context):
        if self.pending is None:
            return
        pending = self.pending
        target = pending['group']
        event = dict(type='assistant/attempt', seq=target['lastChunkSeq'], time=target['lastChunkTime'],
            data=dict(turn=target['turn'], step=target['step'], stream=stream_of(target)))
        self.emit_generated(target['lastChunkSeq'], event, context)
        self.flush_buffered(pending, context)
        self.pending = None

    def flush_buffered(self, pending, context):
        for event in pending['afterLastChunk']:
            self.emit_source(event, context)
        pending['afterLastChunk'].clear()

    def ensure_cut(self, origin, time, kind, context):
        if not self.header['isSeeded'] or self.target_cut is not UNDEFINED or origin < self.source_cut:
            return
        self.target_cut = self.target_seq
        if origin == self.source_cut and kind == 'session/end-seed':
            return
        call(context, 'emitEvent', dict(type='session/end-seed', seq=self.target_seq, time=time, data=dict(inherited=True)))
        self.target_seq += 1

    def emit_source(self, event, context):
        if self.header['isSeeded'] and event['seq'] == self.source_cut and event['type'] == 'session/end-seed':
            event = dict(event, data=dict(inherited=True))
        self.ensure_cut(event['seq'], event['time'], event['type'], context)
        self.mapping[event['seq']] = self.target_seq
        call(context, 'emitEvent', self.remap(event))
        self.target_seq += 1

    def emit_generated(self, origin, event, context):
        self.ensure_cut(origin, event['time'], event['type'], context)
        call(context, 'emitEvent', self.remap(event))
        self.target_seq += 1

    def map_one(self, value, label):
        mapped = self.mapping.get(value, UNDEFINED)
        if mapped is UNDEFINED:
            raise refusal(label + ' targets consumed assistant/chunk %s' % value)
        return mapped

    def remap(self, source):
        kind, seq = source['type'], source['seq']
        def one(value, suffix):
            return self.map_one(value, '%s %s %s' % (kind, seq, suffix))
        data = source['data']
        if kind == 'command/done' and data.get('sourceEventSeq', UNDEFINED) is not UNDEFINED:
            data = dict(data, sourceEventSeq=one(data['sourceEventSeq'], 'sourceEventSeq'))
        elif kind in ('compaction/prune', 'compaction/summary'):
            span = data['shadowedRange']
            data = dict(data, shadowedRange=dict(start=one(span['start'], 'shadowedRange start'), end=one(span['end'], 'shadowedRange end')),
                shadowedSeqs=[one(n, 'shadowedSeqs') for n in data['shadowedSeqs']])
        elif kind in ('session/title', 'session/title-llm-request'):
            data = dict(data, messageSeqs=[one(n, 'messageSeqs') for n in data['messageSeqs']])
        event = {key: value for key, value in source.items() if key not in ('sourceEventSeqs', 'surfaceOp')}
        event.update(seq=self.target_seq, data=data)
        sources = source.get('sourceEventSeqs', UNDEFINED)
        if sources is not UNDEFINED:
            event['sourceEventSeqs'] = [one(n, 'sources') for n in sources]
        operation = source.get('surfaceOp', UNDEFINED)
        if operation is not UNDEFINED:
            event['surfaceOp'] = 'append' if operation == 'append' else dict(op='replace',
                start=one(operation['start'], 'surface start'), end=one(operation['end'], 'surface end'))
        return event


def migrate_header(header):
    assertReleasedV1Header(header)
    return dict(header, version=2)


sessionFormatV1ToV2 = defineSessionFormatMigration(dict(name='@deepseek-ai/dsh-session-format-v1-to-v2',
    fromVersion=1, toVersion=2, migrateHeader=migrate_header, createStage=ReleasedV1ToV2Stage,
    validateTargetHeader=assertReleasedV2Header))
