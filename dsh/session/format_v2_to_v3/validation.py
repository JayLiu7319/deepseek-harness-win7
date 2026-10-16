"""Native v3 system ownership and frozen non-system relationship validation."""
from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import _js_strict_equal
from dsh.session.format import SessionFormatError, SessionFormatUnsupportedMigrationError
from dsh.session.format_v0_to_v1.payload import compact
from dsh.session.format_v1_to_v2 import assertReleasedV2Header, restoreReleasedV2Artifact
from .payload import assertV3Event, isRepairIdentity, record, SURFACE_TYPES


def assertReleasedV3Header(header):
    if not _js_strict_equal(header.get('version', UNDEFINED), 3):
        raise SessionFormatError('expected format v3 header')
    assertReleasedV2Header(dict(header, version=2))


def assertV3EventAdmission(event):
    if event.get('type') in ('tool/code-dispatch-start', 'tool/code-dispatch') and event.get('ignorable') is not True:
        raise SessionFormatUnsupportedMigrationError('format v3 contains unknown event type ' + compact(event['type']) + ' at seq ' + str(event.get('seq', 'undefined')))


def relationship_event(event):
    kind = event['type']
    if kind in ('tool/ptc-dispatch-start', 'tool/ptc-dispatch'):
        return dict(event, type=kind.replace('tool/ptc-', 'tool/code-', 1))
    if kind in ('tool/code-dispatch-start', 'tool/code-dispatch'):
        assertV3EventAdmission(event)
        return dict(event, type='v3/opaque-released-event')
    if kind == 'system/message':
        message = record(record(event['data'], 'system data')['message'], 'system message')
        return dict(event, type='user/message', data=dict(message, role='user'))
    if kind != 'tool/result':
        return event
    data = record(event['data'], 'tool result')
    if data.get('error', UNDEFINED) is UNDEFINED:
        return event
    error = record(data['error'], 'tool error')
    if error.get('code') != 'TOOL_NOT_STARTED':
        return event
    message = record(data['message'], 'tool message')
    source = record(message['source'], 'tool source')
    call_id = source.get('callId', UNDEFINED)
    if not isRepairIdentity(message.get('id', UNDEFINED), call_id):
        return event
    return dict(event, data=dict(data, message=dict(message, id='interrupted-tool-result-' + call_id + '-' + str(event['seq']))))


def restoreReleasedV3Artifact(artifact, knownEventTypes):
    assertReleasedV3Header(artifact['header'])
    step, head, has_surface, events = None, UNDEFINED, False, []
    for event in artifact['events']:
        assertV3EventAdmission(event)
        assertV3Event(event, knownEventTypes)
        kind = event['type']
        if kind == 'step/start':
            data = record(event['data'], kind)
            step = dict(turn=data.get('turn', UNDEFINED), step=data.get('step', UNDEFINED))
        elif kind in ('step/end', 'turn/end'):
            step = None
        if kind == 'system/message':
            data = record(event['data'], kind)
            if step is None or any(not _js_strict_equal(step[key], data.get(key, UNDEFINED)) for key in ('turn', 'step')):
                raise SessionFormatError('system/message does not match an open step')
            operation = event['surfaceOp']
            if has_surface and head is UNDEFINED:
                raise SessionFormatError('system/message requires a protected first surface head')
            if operation == 'append':
                if not has_surface:
                    head = event['seq']
            else:
                replacement = record(operation, 'system replacement')
                if any(_js_strict_equal(replacement[key], head) for key in ('startSeq', 'endSeq')):
                    if not all(_js_strict_equal(replacement[key], head) for key in ('startSeq', 'endSeq')):
                        raise SessionFormatError('system/message must replace exactly the current system head')
                    head = event['seq']
        elif kind in SURFACE_TYPES and event['surfaceOp'] != 'append':
            replacement = record(event['surfaceOp'], 'surface replacement')
            if any(_js_strict_equal(replacement[key], head) for key in ('startSeq', 'endSeq')):
                raise SessionFormatError('surface replacement cannot shadow the protected system head')
        if kind in ('compaction/prune', 'compaction/summary'):
            data = record(event['data'], kind)
            seqs = data.get('shadowedSeqs')
            if isinstance(seqs, list) and any(_js_strict_equal(seq, head) for seq in seqs):
                raise SessionFormatError('compaction cannot shadow the protected system head')
        if kind in SURFACE_TYPES:
            has_surface = True
        projected = relationship_event(event)
        if kind in SURFACE_TYPES and event['surfaceOp'] != 'append':
            replacement = event['surfaceOp']
            projected = dict(projected, surfaceOp=dict(op='replace', start=replacement['startSeq'], end=replacement['endSeq']))
        events.append(projected)
    restoreReleasedV2Artifact(dict(artifact, header=dict(artifact['header'], version=2), events=events), knownEventTypes, 3)
    return artifact
