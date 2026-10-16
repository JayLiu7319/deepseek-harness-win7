"""Released v2 envelope/restoration policy; writer-image checks stay explicit."""
from dsh.core.session.json import UNDEFINED, deep_freeze
from dsh.cordis.utils import _js_strict_equal
from dsh.llm.assistant_stream import expandAssistantStream
from dsh.llm.assembler import BlockAssembler
from dsh.session.format import (SessionFormatError, SessionFormatUnsupportedMigrationError,
    sessionFormatCount, sessionFormatSafeInteger, snapshotSessionFormatJson)
from dsh.session.format_v0_to_v1 import (RELEASED_V0_EVENT_DISPOSITIONS,
    assertReleasedArtifactRelationships, assertReleasedSurfaceMetadata, assertReleasedPayloadSemantics)
from dsh.session.format_v0_to_v1.payload import equal_json, compact
from .codec import assertReleasedV2Header, record, exact_keys

RELEASED_V2_EVENT_DISPOSITIONS = deep_freeze(dict(
    {key: value for key, value in RELEASED_V0_EVENT_DISPOSITIONS.items() if key not in (
        'assistant/chunk', 'assistant/message', 'session-log-deepseek/delivery-accepted', 'session/end-seed')},
    **{
        'assistant/attempt': dict(required=['turn', 'step', 'stream'], optional=[], opaque=[]),
        'assistant/message': dict(required=['turn', 'step', 'message', 'stream'], optional=['usage', 'interrupted'], opaque=[]),
        'session-log-deepseek/delivery-accepted': dict(required=['sessionId', 'throughSeq'], optional=['sessionFormatVersion'], opaque=[]),
        'session/end-seed': dict(required=[], optional=['inherited'], opaque=[]),
    }))
RELEASED_V2_EVENT_TYPES = tuple(sorted(RELEASED_V2_EVENT_DISPOSITIONS))
SURFACE_TYPES = frozenset(('user/message', 'assistant/message', 'tool/result'))


def validate_artifact(artifact, mode, knownEventTypes=None, relationshipHeaderVersion=None):
    assertReleasedV2Header(artifact['header'])
    cut = sessionFormatCount(artifact.get('inheritedEventCount', UNDEFINED), 'format v2 inherited event count')
    if cut > len(artifact['events']):
        raise SessionFormatError('format v2 inherited event count exceeds its events')
    if not artifact['header']['isSeeded'] and cut != 0:
        raise SessionFormatError('unseeded format v2 Session has inherited events')
    last = UNDEFINED
    for index, event in enumerate(artifact['events']):
        value = record(event, 'format v2 event %s' % index)
        kind = value.get('type', UNDEFINED)
        if not isinstance(kind, str):
            raise SessionFormatError('format v2 event %s type must be a string' % index)
        disposition = RELEASED_V2_EVENT_DISPOSITIONS.get(kind)
        installed = knownEventTypes is not None and kind in knownEventTypes
        ignorable = disposition is None and value.get('ignorable') is True
        if mode == 'current' and disposition is None and not installed and not ignorable:
            raise SessionFormatUnsupportedMigrationError('format v2 contains unknown event type %s at seq %s' % (compact(kind), index))
        surface = disposition is not None and kind in SURFACE_TYPES
        admitted = ['ignorable', 'sourceEventSeqs', 'surfaceOp'] if mode == 'physical' or disposition is None or surface else ['ignorable']
        exact_keys(value, ['type', 'seq', 'time', 'data'], admitted, 'format v2 event %s' % index, logical=True)
        if not _js_strict_equal(value['seq'], index):
            raise SessionFormatError('format v2 event %s is not dense' % index)
        sessionFormatSafeInteger(value['time'], 'format v2 event %s time' % index)
        if value.get('ignorable', UNDEFINED) is not UNDEFINED and value['ignorable'] is not True:
            raise SessionFormatError('format v2 event %s ignorable must be true when present' % index)
        if kind == 'session/end-seed':
            data = record(event['data'], 'session/end-seed %s data' % index)
            if data.get('inherited') is True:
                last = index
    if artifact['header']['isSeeded'] and not _js_strict_equal(last, cut):
        raise SessionFormatError('format v2 seeded header disagrees with its last inherited end-seed marker')
    if not artifact['header']['isSeeded'] and last is not UNDEFINED:
        raise SessionFormatError('format v2 unseeded Session contains an inherited end-seed marker')
    if mode == 'current':
        version = artifact['header']['version'] if relationshipHeaderVersion is None else relationshipHeaderVersion
        assertReleasedArtifactRelationships(dict(artifact, header=dict(artifact['header'], version=version)),
            dict(stepEvents={'assistant/attempt'}, preservedSourceTitleRequestText=True))


def restoreReleasedV2Artifact(artifact, knownEventTypes, relationshipHeaderVersion=None):
    validate_artifact(artifact, 'current', knownEventTypes, relationshipHeaderVersion)
    return artifact


def assertReleasedV2PhysicalArtifact(artifact):
    validate_artifact(artifact, 'physical')


def assertReleasedV2WriterArtifact(artifact):
    """Frozen writer image used to qualify migrations, matching Source test validation.

    The ordinary installed-vocabulary restorer intentionally remains less strict
    about plugin payload additions, as upstream requires.
    """
    assertReleasedV2PhysicalArtifact(artifact)
    for index, event in enumerate(artifact['events']):
        kind = event['type']
        disposition = RELEASED_V2_EVENT_DISPOSITIONS.get(kind)
        if disposition is None:
            raise SessionFormatUnsupportedMigrationError('format v2 contains unknown event type %s at seq %s' % (compact(kind), index))
        if kind in SURFACE_TYPES:
            assertReleasedSurfaceMetadata(event, index, kind, 'forbid-assistant')
        assert_writer_payload(event, disposition)
    restoreReleasedV2Artifact(artifact, RELEASED_V2_EVENT_TYPES)


def assert_writer_payload(event, disposition):
    kind, seq = event['type'], event['seq']
    data = record(event['data'], '%s %s data' % (kind, seq))
    exact_keys(data, disposition['required'], disposition['optional'], '%s %s data' % (kind, seq), logical=True)
    for key in disposition['opaque']:
        if key in data:
            snapshotSessionFormatJson(data[key], '%s %s opaque %s' % (kind, seq, key))
    if kind in ('assistant/attempt', 'assistant/message'):
        turn = sessionFormatCount(data['turn'], '%s %s turn' % (kind, seq))
        step = sessionFormatCount(data['step'], '%s %s step' % (kind, seq))
        assembler = BlockAssembler()
        try:
            timed = expandAssistantStream(data['stream'])
            for value in timed:
                assertReleasedPayloadSemantics(dict(type='assistant/chunk', seq=seq, time=value['time'],
                    data=dict(turn=turn, step=step, chunk=value['chunk'])), 2)
                assembler.push(value['chunk'])
        except Exception as error:
            failure = SessionFormatError('%s %s has an invalid embedded stream' % (kind, seq))
            failure.cause = error
            raise failure from error
        if kind == 'assistant/attempt':
            return
        assertReleasedPayloadSemantics(event, 2)
        if timed:
            message = record(data['message'], 'assistant/message %s message' % seq)
            content = assembler.interruptedBlocks() if data.get('interrupted') is True else assembler.blocks()
            if not equal_json(message['content'], content):
                raise SessionFormatError('assistant/message %s message content disagrees with its embedded stream' % seq)
            if not equal_json(data.get('usage', UNDEFINED), assembler.usage):
                raise SessionFormatError('assistant/message %s usage disagrees with its embedded stream' % seq)
            source = record(message['source'], 'assistant/message %s source' % seq)
            if not equal_json(source.get('replayState', UNDEFINED), assembler.replayState):
                raise SessionFormatError('assistant/message %s replay state disagrees with its embedded stream' % seq)
        return
    if kind == 'session/end-seed':
        if data.get('inherited', UNDEFINED) is not UNDEFINED and data['inherited'] is not True:
            raise SessionFormatError('session/end-seed %s inherited must be true when present' % seq)
        return
    assertReleasedPayloadSemantics(event, 2)
