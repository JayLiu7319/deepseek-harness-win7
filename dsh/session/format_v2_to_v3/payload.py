"""Audited v2 admission and canonical v3 structural envelopes."""
import re

from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import js_to_string
from dsh.session.format import SessionFormatError, SessionFormatUnsupportedMigrationError, sessionFormatCount, sessionFormatSafeInteger
from dsh.session.format_v0_to_v1 import assertReleasedPayloadSemantics, assertReleasedSurfaceMetadata
from dsh.session.format_v0_to_v1.payload import compact
from dsh.session.format_v1_to_v2.validation import RELEASED_V2_EVENT_DISPOSITIONS
from dsh.session.format_v1_to_v2.codec import record, exact_keys

SURFACE_TYPES = frozenset(('system/message', 'user/message', 'assistant/message', 'tool/result'))
SOURCE_KINDS = frozenset(('user', 'plugin', 'model', 'tool', 'agent-instructions', 'session-reference', 'team-message', 'goal', 'skill-invocation', 'skill-catalog', 'coordinator', 'subagent-report', 'subagent-settled', 'webhook', 'agent-message'))
CONTENT_KINDS = frozenset(('text', 'reasoning', 'image', 'file', 'tool-call', 'tool-result'))


def display(value):
    return 'undefined' if value is UNDEFINED else js_to_string(value)


def keys(value, required, optional, label):
    exact_keys(value, required, optional, label, logical=True)


def isRepairIdentity(identity, call_id):
    if not isinstance(call_id, str) or not isinstance(identity, str):
        return False
    prefix = 'interrupted-tool-result-' + call_id + '-'
    if not identity.startswith(prefix):
        return False
    suffix = identity[len(prefix):]
    return re.fullmatch(r'(0|[1-9][0-9]*)', suffix) is not None and len(suffix) <= 16 and int(suffix) <= 9007199254740991


def assert_source(message):
    source = record(message.get('source', UNDEFINED), 'message source')
    kind = source.get('kind')
    if not isinstance(kind, str) or kind not in SOURCE_KINDS:
        raise SessionFormatUnsupportedMigrationError('cannot safely transform unclassified message source')
    if kind == 'agent-message':
        keys(source, ['kind', 'form', 'senderSessionId'], [], 'agent-message source')
        if source['form'] != 'relay' or not isinstance(source['senderSessionId'], str) or not source['senderSessionId']:
            raise SessionFormatError('agent-message source requires relay form and senderSessionId')


def content_array(value, label):
    if not isinstance(value, list):
        raise SessionFormatError(label + ': content must be an array')
    return value


def assert_content_kind(kind, label):
    if not isinstance(kind, str) or kind not in CONTENT_KINDS:
        rendered = 'undefined' if kind is UNDEFINED else compact(kind)
        raise SessionFormatUnsupportedMigrationError(label + ': cannot safely transform unclassified message content kind ' + rendered)


def assert_content(value, label):
    for index, child in enumerate(content_array(value, label)):
        assert_content_block(child, label + '[%s]' % index)


def assert_content_block(value, label):
    block = record(value, label)
    kind = block.get('type', UNDEFINED)
    assert_content_kind(kind, label)
    if kind == 'tool-result':
        if not isinstance(block.get('content'), list):
            raise SessionFormatError(label + '.content: invalid message content kind "tool-result": content must be an array')
        assert_content(block['content'], label + '.content')
    if kind == 'file':
        keys(block, ['type', 'attachment'], [], label + ' kind "file"')
        attachment = record(block['attachment'], label + ' kind "file" attachment')
        keys(attachment, ['attachmentId', 'name', 'bytes'], [], label + ' kind "file" attachment')
        if not isinstance(attachment['attachmentId'], str) or not attachment['attachmentId'] or not isinstance(attachment['name'], str):
            raise SessionFormatError(label + ' kind "file": file attachment requires attachmentId and name')
        sessionFormatCount(attachment['bytes'], label + ' kind "file" attachment bytes')
        return
    leaf = dict(block, content=[]) if kind == 'tool-result' else block
    probe = dict(type='user/message', seq=0, time=0, data=dict(id='content-admission', role='user', source=dict(kind='user'), content=[leaf]))
    try:
        assertReleasedPayloadSemantics(probe, 2)
    except Exception as error:
        raise SessionFormatError(label + ': invalid message content kind ' + compact(kind) + ': ' + getattr(error, 'name', 'Error') + ': ' + str(error)) from None


def assert_owned_content(event, data):
    kind = event['type']
    label = 'format v2 %s at seq %s data' % (kind, event['seq'])
    if kind in ('user/message', 'tool/code-dispatch'):
        assert_content(data.get('content', UNDEFINED), label + '.content')
    elif kind in ('assistant/message', 'tool/result', 'team/message/queued'):
        assert_content(record(data.get('message', UNDEFINED), label + '.message').get('content', UNDEFINED), label + '.message.content')
    elif kind in ('agent/inbox/spliced', 'session/title-llm-request'):
        field = 'inserted' if kind == 'agent/inbox/spliced' else 'messages'
        for index, value in enumerate(content_array(data.get(field, UNDEFINED), label + '.' + field)):
            path = label + '.' + field + '[%s]' % index
            assert_content(record(value, path).get('content', UNDEFINED), path + '.content')
    elif kind == 'compaction/summary':
        assert_content(data.get('summary', UNDEFINED), label + '.summary')
        if data.get('rawOutput', UNDEFINED) is not UNDEFINED:
            assert_content(data['rawOutput'], label + '.rawOutput')
    if kind in ('assistant/message', 'assistant/attempt'):
        for index, value in enumerate(content_array(data.get('stream', UNDEFINED), label + '.stream')):
            path = label + '.stream[%s]' % index
            entry = record(value, path)
            if entry.get('type') != 'chunk':
                continue
            chunk = record(entry.get('chunk', UNDEFINED), path + '.chunk')
            if chunk.get('type') == 'block-end':
                assert_content_block(chunk.get('block', UNDEFINED), path + '.chunk.block')
            if chunk.get('type') == 'block-start':
                assert_content_kind(chunk.get('blockType', UNDEFINED), path + '.chunk.blockType')


def assert_feedback(kind, data):
    keys(data, ['sessionId', 'item'] if kind == 'feedback/message-put' else ['sessionId', 'messageId'], [], kind)
    if not isinstance(data['sessionId'], str):
        raise SessionFormatError('feedback sessionId must be a string')
    if kind == 'feedback/message-delete':
        if not isinstance(data['messageId'], str):
            raise SessionFormatError('feedback messageId must be a string')
        return
    item = record(data['item'], 'feedback item')
    keys(item, ['messageId', 'rating', 'version', 'createdAt', 'updatedAt'], ['note'], 'feedback item')
    for key in ('messageId', 'version'):
        if not isinstance(item[key], str):
            raise SessionFormatError('feedback ' + key + ' must be a string')
    if item['rating'] not in ('positive', 'negative'):
        raise SessionFormatError('invalid feedback rating')
    if item.get('note', UNDEFINED) is not UNDEFINED and not isinstance(item['note'], str):
        raise SessionFormatError('feedback note must be a string')
    sessionFormatCount(item['createdAt'], 'feedback createdAt')
    sessionFormatCount(item['updatedAt'], 'feedback updatedAt')


def assertEvent(event, version):
    if version == 3:
        assertV3Event(event)
        return
    kind = event.get('type', UNDEFINED)
    disposition = RELEASED_V2_EVENT_DISPOSITIONS.get(kind) if isinstance(kind, str) else None
    feedback = kind in ('feedback/message-put', 'feedback/message-delete')
    if disposition is None and not feedback:
        raise SessionFormatUnsupportedMigrationError('format v2 to v3 cannot safely transform unclassified event ' + display(kind))
    surface = kind in SURFACE_TYPES
    keys(event, ['type', 'seq', 'time', 'data'], ['ignorable', 'sourceEventSeqs', 'surfaceOp'] if surface else ['ignorable'], kind)
    sessionFormatCount(event['seq'], 'event seq')
    sessionFormatSafeInteger(event['time'], 'event time')
    if event.get('ignorable', UNDEFINED) is not UNDEFINED and event['ignorable'] is not True:
        raise SessionFormatError('ignorable must be true')
    if surface:
        assertReleasedSurfaceMetadata(event, event['seq'], kind, 'forbid-assistant')
        if event.get('surfaceOp', UNDEFINED) is UNDEFINED:
            raise SessionFormatError(kind + ' requires surfaceOp')
    data = record(event['data'], kind + ' data')
    if feedback:
        assert_feedback(kind, data)
        return
    keys(data, disposition['required'], disposition['optional'], kind + ' data')
    assert_owned_content(event, data)
    if kind != 'assistant/attempt':
        assertReleasedPayloadSemantics(event, version)
    if kind in ('assistant/message', 'assistant/attempt'):
        for coordinate in ('turn', 'step'):
            if sessionFormatCount(data.get(coordinate, UNDEFINED), coordinate) == 0:
                raise SessionFormatError(coordinate + ' must be positive')
    if kind == 'session/end-seed' and data.get('inherited', UNDEFINED) is not UNDEFINED and data['inherited'] is not True:
        raise SessionFormatError('session/end-seed inherited must be true')
    if kind == 'user/message':
        assert_source(data)
    if kind in ('assistant/message', 'tool/result'):
        assert_source(record(data['message'], 'message'))
    if kind == 'tool/result' and isinstance(data.get('error'), dict) and data['error'].get('code') == 'TOOL_NOT_STARTED':
        message = record(data['message'], 'tool result message')
        source = record(message['source'], 'tool result source')
        if not isRepairIdentity(message['id'], source.get('callId', UNDEFINED)):
            raise SessionFormatError('TOOL_NOT_STARTED repair requires its canonical historical message id')
    if kind in ('agent/inbox/spliced', 'session/title-llm-request'):
        for message in data['inserted' if kind == 'agent/inbox/spliced' else 'messages']:
            assert_source(message)


def assert_system(event, data):
    keys(data, ['turn', 'step', 'message'], [], 'system/message data')
    for coordinate in ('turn', 'step'):
        if sessionFormatCount(data[coordinate], coordinate) == 0:
            raise SessionFormatError(coordinate + ' must be positive')
    message = record(data['message'], 'system message')
    keys(message, ['id', 'role', 'source', 'content'], [], 'system message')
    if not isinstance(message['id'], str) or not message['id'] or message['role'] != 'system':
        raise SessionFormatError('system message requires an id and system role')
    source = record(message['source'], 'system source')
    if source.get('kind') != 'plugin' or not isinstance(source.get('plugin'), str) or not source['plugin']:
        raise SessionFormatError('system message requires plugin source')
    assertReleasedPayloadSemantics(dict(event, type='user/message', data=dict(message, role='user')), 3)


def assertV3StructuralRow(value):
    if not isinstance(value, dict):
        return
    if value.get('type') == 'request/header':
        data = record(value.get('data', UNDEFINED), 'request/header data')
        if 'system' in record(data.get('header', UNDEFINED), 'request header'):
            raise SessionFormatUnsupportedMigrationError('format v3 request/header rejects retired header.system')
    elif value.get('type') == 'system/message':
        data = record(value.get('data', UNDEFINED), 'system/message data')
        assert_system(dict(type='system/message', seq=0, time=0, data=data), data)


def assertV3Event(event, knownEventTypes=None):
    value = record(event, 'format v3 event')
    kind, seq = value.get('type', UNDEFINED), value.get('seq', UNDEFINED)
    subject = 'format v3 %s at seq %s' % (display(kind), display(seq))
    obsolete = kind in ('tool/code-dispatch-start', 'tool/code-dispatch')
    known = not obsolete and isinstance(kind, str) and (kind in SURFACE_TYPES or kind in RELEASED_V2_EVENT_DISPOSITIONS
        or kind in ('tool/ptc-dispatch-start', 'tool/ptc-dispatch', 'feedback/message-put', 'feedback/message-delete') or knownEventTypes is not None and kind in knownEventTypes)
    surface = isinstance(kind, str) and kind in SURFACE_TYPES
    keys(value, ['type', 'seq', 'time', 'data'], ['ignorable', 'surfaceOp', 'sourceEventSeqs'] if surface or not known else ['ignorable'], subject)
    if not isinstance(kind, str):
        raise SessionFormatError(subject + ' type must be a string')
    sessionFormatCount(seq, subject + ' seq')
    sessionFormatSafeInteger(event['time'], subject + ' time')
    if 'ignorable' in value and value['ignorable'] is not True:
        raise SessionFormatError(subject + ' ignorable must be true when present')
    if surface:
        operation = value.get('surfaceOp', UNDEFINED)
        if operation is UNDEFINED:
            raise SessionFormatError(subject + ' requires a surfaceOp marker')
        if operation != 'append':
            replacement = record(operation, subject + ' surfaceOp')
            if len(replacement) != 3 or replacement.get('op') != 'replace' or 'startSeq' not in replacement or 'endSeq' not in replacement:
                raise SessionFormatError(subject + ' requires exact replace fields op/startSeq/endSeq')
            for key in ('startSeq', 'endSeq'):
                if sessionFormatCount(replacement[key], subject + ' surfaceOp ' + key) >= seq:
                    raise SessionFormatError(subject + ' replacement endpoints must reference earlier events')
        sources = value.get('sourceEventSeqs', UNDEFINED)
        if kind == 'assistant/message' and sources is not UNDEFINED:
            raise SessionFormatError(subject + ' embeds its stream and cannot carry sourceEventSeqs')
        if sources is not UNDEFINED:
            if not isinstance(sources, list) or not sources:
                raise SessionFormatError(subject + ' sourceEventSeqs must be a non-empty array')
            seen = set()
            for source in sources:
                current = sessionFormatCount(source, subject + ' sourceEventSeqs member')
                if current >= seq or current in seen:
                    raise SessionFormatError(subject + ' sourceEventSeqs must be unique earlier seqs')
                seen.add(current)
    assertV3StructuralRow(event)
    if kind == 'request/header':
        data = record(event['data'], subject + ' data')
        header = record(data.get('header', UNDEFINED), subject + ' header')
        if isinstance(header.get('tools'), list) and not header['tools'] or isinstance(header.get('adapterDefaults'), dict) and not header['adapterDefaults']:
            raise SessionFormatError(subject + ' empty optional header fields must be omitted')
    if kind == 'tool/result':
        data = record(event['data'], subject + ' data')
        if data.get('error', UNDEFINED) is UNDEFINED:
            return
        message = record(data.get('message', UNDEFINED), subject + ' message')
        content = message.get('content')
        if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict) or content[0].get('type') != 'tool-result' or content[0].get('isError') is not True:
            raise SessionFormatError(subject + ' carries error metadata for a non-error tool result')


def canonicalizeTransformedEvent(event):
    target = event
    operation = event.get('surfaceOp', UNDEFINED)
    if operation is not UNDEFINED and operation != 'append':
        label = 'format v2 %s at seq %s' % (event['type'], event['seq'])
        replacement = record(operation, label + ' surfaceOp')
        if len(replacement) != 3 or replacement.get('op') != 'replace' or 'start' not in replacement or 'end' not in replacement:
            raise SessionFormatError(label + ' requires exact replace fields op/start/end')
        target = dict(event, surfaceOp=dict(op='replace', startSeq=sessionFormatCount(replacement['start'], label + ' replace start'), endSeq=sessionFormatCount(replacement['end'], label + ' replace end')))
    if event['type'] == 'request/header':
        data = record(event['data'], 'format v2 request/header at seq %s data' % event['seq'])
        header = record(data.get('header', UNDEFINED), 'format v2 request/header at seq %s header' % event['seq'])
        empty = [key for key in header if key == 'tools' and isinstance(header[key], list) and not header[key] or key == 'adapterDefaults' and isinstance(header[key], dict) and not header[key]]
        if empty:
            target = dict(target, data=dict(data, header={key: value for key, value in header.items() if key not in empty}))
    assertV3Event(target)
    return target
