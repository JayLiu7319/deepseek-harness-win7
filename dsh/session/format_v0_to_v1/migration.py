"""Streaming released-v0 normalization into the shared-layout v1 format."""
from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import _js_strict_equal
from dsh.session.format import SessionFormatError, SessionFormatUnsupportedMigrationError, defineSessionFormatMigration, sessionFormatCount
from dsh.session.format.chain import member, call
from .codec import record, exact_keys, isReleasedAssistantChunkRun
from .payload import compact
from .validation import assertReleasedEventPayload, assertReleasedV1Header


def header_version(header, version):
    if not _js_strict_equal(header.get('version', UNDEFINED), version):
        raise SessionFormatError('expected format v%s header' % version)


def malformed(session_id, kind, seq):
    return SessionFormatError('session %s contains malformed pre-react-loop %s at seq %s' % (compact(session_id), kind, seq))


def normalize_turn_end(event, session_id):
    if event['type'] != 'turn/end':
        return event
    seq = event['seq']
    data = record(event['data'], 'turn/end %s data' % seq)
    exact_keys(data, ['turn', 'reason'], [], 'turn/end %s data' % seq)
    turn = sessionFormatCount(data['turn'], 'turn/end %s turn' % seq)
    if turn < 1:
        raise malformed(session_id, 'turn/end', seq)
    reason = record(data['reason'], 'turn/end %s reason' % seq)
    kind = reason.get('kind', UNDEFINED)
    if not isinstance(kind, str):
        raise malformed(session_id, 'turn/end', seq)
    if kind in ('completed', 'blocked', 'max-tokens', 'interrupted'):
        exact_keys(reason, ['kind'], [], 'turn/end %s reason' % seq)
        return event
    if kind == 'aborted':
        if 'reason' in reason:
            return event
        exact_keys(reason, ['kind'], [], 'turn/end %s reason' % seq)
        current = dict(kind='aborted', reason=dict(kind='legacy'))
    elif kind == 'disposed':
        exact_keys(reason, ['kind'], [], 'turn/end %s reason' % seq)
        current = dict(kind='aborted', reason=dict(kind='disposed'))
    elif kind == 'error':
        if 'error' in reason:
            return event
        sessionFormatCount(reason.get('step', UNDEFINED), 'turn/end %s error step' % seq)
        if reason.get('failure', UNDEFINED) is not UNDEFINED:
            exact_keys(reason, ['kind', 'step', 'failure'], [], 'turn/end %s reason' % seq)
            failure = record(reason['failure'], 'turn/end %s failure' % seq)
            exact_keys(failure, ['message', 'code'], ['status', 'providerRetryAfterMs', 'requestId'], 'turn/end %s failure' % seq)
            if not isinstance(failure['message'], str) or not isinstance(failure['code'], str):
                raise malformed(session_id, 'turn/end', seq)
            current = dict(kind='error', error=failure)
        else:
            exact_keys(reason, ['kind', 'step', 'message'], ['code'], 'turn/end %s reason' % seq)
            if not isinstance(reason['message'], str) or reason.get('code', UNDEFINED) is not UNDEFINED and not isinstance(reason['code'], str):
                raise malformed(session_id, 'turn/end', seq)
            current = dict(kind='error', error=dict(message=reason['message'], code=reason.get('code', 'UNKNOWN')))
    else:
        return event
    return dict(event, data=dict(data, reason=current))


class ReleasedV0ToV1Stage:
    def __init__(self, source):
        self.source = source
        self.header = member(source, 'sourceHeader')
        header_version(self.header, 0)
        self.headerInheritedEventCount = sessionFormatCount(member(source, 'sourceInheritedEventCount'), 'format v0 inherited event count')
        self.message_ids, self.retry_ids = {}, {}
        self.compaction_id = UNDEFINED

    def transformEvent(self, event, context):
        event = self.normalize(event)
        if event['type'] == 'session-log-deepseek/delivery-accepted':
            data = record(event['data'], '%s %s data' % (event['type'], event['seq']))
            accepted = data.get('sessionFormatVersion')
            accepted = 0 if accepted is None else accepted
            inherited = self.header.get('parentSession', UNDEFINED) is not UNDEFINED and event['seq'] < self.headerInheritedEventCount
            if _js_strict_equal(accepted, 0) and not inherited and data['sessionId'] != self.header['id']:
                raise SessionFormatError('current-generation delivery marker names the wrong Session')
        call(context, 'emitEvent', event)

    def transformRun(self, run, context):
        if isReleasedAssistantChunkRun(run):
            call(context, 'emitRun', run)
        else:
            for event in call(run, 'expand'):
                self.transformEvent(event, context)

    def finish(self, context):
        return self.headerInheritedEventCount

    def normalize(self, event):
        session_id, seq = self.header['id'], event['seq']
        if event['type'] in ('compact/start', 'compact/summary', 'compact/end', 'compact/prune'):
            event = dict(event, type='compaction/' + event['type'].split('/')[1])
        kind = event['type']
        if kind in ('request/header-delta', 'mode/set'):
            raise SessionFormatUnsupportedMigrationError('session %s contains unsupported legacy %s event at seq %s' % (compact(session_id), kind, seq))
        if kind == 'request/header':
            data = record(event['data'], 'request/header %s data' % seq)
            if data.get('reason') == 'fallback':
                raise SessionFormatUnsupportedMigrationError('session %s contains unsupported request/header reason "fallback" at seq %s' % (compact(session_id), seq))
        if kind == 'turn/start':
            data = record(event['data'], 'turn/start %s data' % seq)
            if 'trigger' in data:
                exact_keys(data, ['turn', 'trigger'], [], 'turn/start %s data' % seq)
                turn = sessionFormatCount(data['turn'], 'turn/start %s turn' % seq)
                trigger = record(data['trigger'], 'turn/start %s trigger' % seq)
                if turn < 1 or not isinstance(trigger.get('kind'), str) or not trigger['kind']:
                    raise malformed(session_id, kind, seq)
                event = dict(event, data=dict(turn=turn))
        event = normalize_turn_end(event, session_id)
        if kind == 'request/header':
            data = record(event['data'], 'request/header %s data' % seq)
            header = record(data.get('header', UNDEFINED), 'request/header %s header' % seq)
            if 'messagePrefix' in header:
                if not isinstance(header['messagePrefix'], list):
                    raise SessionFormatError('session %s contains malformed request/header messagePrefix at seq %s' % (compact(session_id), seq))
                event = dict(event, data=dict(data, header={key: value for key, value in header.items() if key != 'messagePrefix'}))
        if kind == 'steering/message':
            data = record(event['data'], 'steering/message %s data' % seq)
            if data.get('message', UNDEFINED) is not UNDEFINED:
                exact_keys(data, ['turn', 'message'], [], 'steering/message %s data' % seq)
                sessionFormatCount(data['turn'], 'steering/message %s turn' % seq)
                event = dict(event, type='user/message', data=data['message'])
            else:
                exact_keys(data, ['turn', 'content', 'source'], [], 'steering/message %s data' % seq)
                sessionFormatCount(data['turn'], 'steering/message %s turn' % seq)
                message = {key: value for key, value in data.items() if key != 'turn'}
                event = dict(event, type='user/message', data=dict(message, id=self.message_id(seq), role='user'))
        kind = event['type']
        if kind == 'llm/retry':
            data = record(event['data'], 'llm/retry %s data' % seq)
            chain = '\0'.join('' if data.get(key, UNDEFINED) is UNDEFINED else compact(data[key]) for key in ['turn', 'step', 'provider', 'policyKey'])
            retry_id = data.get('retryId')
            if isinstance(retry_id, str) and retry_id:
                self.retry_ids[chain] = retry_id
            elif 'retryId' not in data:
                retry_id = self.retry_ids.get(chain, 'legacy-retry:%s:%s' % (session_id, seq))
                self.retry_ids[chain] = retry_id
                event = dict(event, data=dict(data, retryId=retry_id))
        if kind == 'session/end-seed':
            self.compaction_id = UNDEFINED
        elif kind == 'compaction/start':
            data = record(event['data'], 'compaction/start %s data' % seq)
            existing = data.get('compactionId')
            if isinstance(existing, str) and existing:
                self.compaction_id = existing
            elif 'compactionId' not in data:
                self.compaction_id = 'legacy-compaction:%s:%s' % (session_id, seq)
                event = dict(event, data=dict(data, compactionId=self.compaction_id))
        elif self.compaction_id is not UNDEFINED:
            if kind in ('compaction/summary', 'compaction/end'):
                data = record(event['data'], '%s %s data' % (kind, seq))
                if 'compactionId' not in data:
                    event = dict(event, data=dict(data, compactionId=self.compaction_id))
                if kind == 'compaction/end':
                    self.compaction_id = UNDEFINED
            elif kind == 'user/message':
                data = record(event['data'], 'user/message %s data' % seq)
                source = data.get('source')
                if isinstance(source, dict) and source.get('kind') == 'plugin' and source.get('plugin') == 'compact' and 'compactionId' not in source:
                    event = dict(event, data=dict(data, source=dict(source, compactionId=self.compaction_id)))
        event = self.normalize_message(event)
        if event['type'] != 'assistant/chunk':
            assertReleasedEventPayload(event, 0)
        data = record(event['data'], '%s %s data' % (event['type'], seq))
        message = data if event['type'] == 'user/message' else data.get('message')
        if isinstance(message, dict) and isinstance(message.get('id'), str):
            self.message_ids[seq] = message['id']
        return event

    def message_id(self, seq):
        return 'legacy-message:%s:%s' % (self.header['id'], seq)

    def normalize_message(self, event):
        kind, seq = event['type'], event['seq']
        data = record(event['data'], '%s %s data' % (kind, seq))
        if kind == 'user/message':
            if any(key in data for key in ['id', 'role', 'message']) or 'content' not in data or 'source' not in data:
                return event
            return dict(event, data=dict(data, id=self.message_id(seq), role='user'))
        if kind == 'assistant/message':
            if 'message' in data or 'content' not in data or 'provenance' not in data:
                return event
            source = record(data['provenance'], 'assistant/message %s provenance' % seq)
            rest = {key: value for key, value in data.items() if key not in ('content', 'provenance')}
            rest['message'] = dict(id=self.message_id(seq), role='assistant', content=data['content'], source=dict(source, kind='model'))
            return dict(event, data=rest)
        if kind == 'tool/result':
            if 'message' in data or any(key not in data for key in ['callId', 'content', 'isError']):
                return event
            if not isinstance(data['callId'], str) or type(data['isError']) is not bool or data['content'] is UNDEFINED:
                return event
            operation = event.get('surfaceOp')
            inherited = operation.get('start', UNDEFINED) if isinstance(operation, dict) and operation.get('op') == 'replace' else UNDEFINED
            message_id = self.message_id(seq) if inherited is UNDEFINED else self.message_ids.get(inherited, UNDEFINED)
            if message_id is UNDEFINED:
                raise SessionFormatError('tool/result %s replacement cites a message without identity' % seq)
            rest = {key: value for key, value in data.items() if key not in ('callId', 'content', 'isError')}
            rest['message'] = dict(id=message_id, role='user', content=[dict(type='tool-result', toolCallId=data['callId'], content=data['content'], isError=data['isError'])], source=dict(kind='tool', callId=data['callId']))
            return dict(event, data=rest)
        return event


def migrate_header(header):
    header_version(header, 0)
    return dict(header, version=1)


sessionFormatV0ToV1 = defineSessionFormatMigration(dict(name='@deepseek-ai/dsh-session-format-v0-to-v1',
    fromVersion=0, toVersion=1, migrateHeader=migrate_header,
    createStage=ReleasedV0ToV1Stage, validateTargetHeader=assertReleasedV1Header))
