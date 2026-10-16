"""rc.3 frozen v2 physical framing and provenance, without event vocabulary policy."""
import os

from dsh.core.session.json import UNDEFINED, FrozenDict
from dsh.cordis.utils import js_to_string
from dsh.session.format import (SessionFormatError, sessionFormatCount, sessionFormatSafeInteger,
    snapshotSessionFormatJson)

HEADER_REQUIRED = ('type', 'version', 'id', 'createdAt', 'isSeeded', 'delegationDepth')
HEADER_OPTIONAL = ('cwd', 'parentSession', 'origin', 'agentPreset')
EVENT_REQUIRED = ('type', 'seq', 'time', 'data')
EVENT_OPTIONAL = ('ignorable', 'sourceEventSeqs', 'surfaceOp')


def record(value, label):
    if not isinstance(value, dict):
        raise SessionFormatError(label + ' must be an object')
    return value


def exact_keys(value, required, optional, label, logical=False):
    allowed = set(required) | set(optional)
    missing = next((key for key in required if key not in value), UNDEFINED)
    if missing is not UNDEFINED:
        raise SessionFormatError(label + (' lacks required field ' if logical else ' lacks ') + missing)
    unexpected = next((key for key in value if key not in allowed), UNDEFINED)
    if unexpected is not UNDEFINED:
        raise SessionFormatError(label + ' has unexpected field ' + unexpected)


def assertReleasedV2Header(header):
    value = record(header, 'format v2 header')
    # The logical validator's wording differs from physical framing.
    exact_keys(value, HEADER_REQUIRED[1:], HEADER_OPTIONAL, 'format v2 header', logical=True)
    if type(value['version']) not in (int, float) or value['version'] != 2:
        raise SessionFormatError('expected format v2 header')
    if not isinstance(value['id'], str):
        raise SessionFormatError('format v2 header id must be a string')
    sessionFormatCount(value['createdAt'], 'format v2 header createdAt')
    sessionFormatCount(value['delegationDepth'], 'format v2 header delegationDepth')
    if type(value['isSeeded']) is not bool:
        raise SessionFormatError('format v2 header isSeeded must be boolean')
    if value.get('cwd', UNDEFINED) is not UNDEFINED and (
            not isinstance(value['cwd'], str) or not os.path.isabs(value['cwd'])):
        raise SessionFormatError('format v2 header cwd must be absolute')
    for key in ('parentSession', 'agentPreset'):
        if value.get(key, UNDEFINED) is not UNDEFINED and not isinstance(value[key], str):
            raise SessionFormatError('format v2 header %s must be a string' % key)
    if value.get('origin', UNDEFINED) is not UNDEFINED and value['origin'] != 'subagent':
        raise SessionFormatError('format v2 header origin must be "subagent"')


def decodePhysicalHeader(value):
    source = record(snapshotSessionFormatJson(value, 'released v2 physical header'), 'released v2 physical header')
    exact_keys(source, HEADER_REQUIRED, HEADER_OPTIONAL, 'released v2 physical header')
    if source['type'] != 'session' or type(source['version']) not in (int, float) or source['version'] != 2:
        raise SessionFormatError('expected released v2 physical Session header')
    if not isinstance(source['id'], str):
        raise SessionFormatError('released v2 header id must be a string')
    created = sessionFormatCount(source['createdAt'], 'released v2 header createdAt')
    depth = sessionFormatCount(source['delegationDepth'], 'released v2 header delegationDepth')
    if type(source['isSeeded']) is not bool:
        raise SessionFormatError('released v2 header isSeeded must be boolean')
    for key in ('cwd', 'parentSession', 'agentPreset'):
        if key in source and not isinstance(source[key], str):
            raise SessionFormatError('released v2 header %s must be a string' % key)
    if 'origin' in source and source['origin'] != 'subagent':
        raise SessionFormatError('released v2 header origin must be "subagent"')
    header = snapshotSessionFormatJson(dict(version=2, id=source['id'], createdAt=created,
        isSeeded=source['isSeeded'], delegationDepth=depth,
        **{key: source[key] for key in HEADER_OPTIONAL if key in source}), 'released v2 logical header')
    assertReleasedV2Header(header)
    return header


def decodeSeqRanges(value, maxEntries):
    if not isinstance(value, list):
        raise SessionFormatError('sourceEventSeqs must be an array')
    output, has_range = [], False
    for entry in value:
        if not isinstance(entry, list):
            output.append(sessionFormatCount(entry, 'sourceEventSeqs member'))
            continue
        if len(entry) != 2:
            raise SessionFormatError('sourceEventSeqs range must be a [start, end] pair')
        first = sessionFormatCount(entry[0], 'sourceEventSeqs range start')
        last = sessionFormatCount(entry[1], 'sourceEventSeqs range end')
        if first > last or last >= maxEntries or last - first + 1 > maxEntries - len(output):
            raise SessionFormatError('sourceEventSeqs range exceeds its event seq')
        output.extend(range(int(first), int(last) + 1))
        has_range = True
    seen = set()
    for source in output:
        if source >= maxEntries or source in seen:
            raise SessionFormatError('sourceEventSeqs ranges must contain unique earlier seqs')
        seen.add(source)
    if has_range and any(output[index] <= output[index-1] for index in range(1, len(output))):
        raise SessionFormatError('sourceEventSeqs ranges must be strictly increasing')
    return output


def decodeEvent(value, rowIndex):
    label = 'released v2 row %s' % rowIndex
    event = record(value, label)
    exact_keys(event, EVENT_REQUIRED, EVENT_OPTIONAL, label, logical=True)
    if not isinstance(event['type'], str):
        raise SessionFormatError(label + ' type must be a string')
    sessionFormatSafeInteger(event['time'], label + ' time')
    if event.get('ignorable', UNDEFINED) is not UNDEFINED and event['ignorable'] is not True:
        raise SessionFormatError(label + ' ignorable must be true when present')
    if event.get('sourceEventSeqs', UNDEFINED) is UNDEFINED:
        return event
    seq = sessionFormatCount(event['seq'], label + ' seq')
    return dict(event, sourceEventSeqs=decodeSeqRanges(event['sourceEventSeqs'], seq))


def encodeSeqRanges(values):
    if any(values[index] <= values[index-1] for index in range(1, len(values))):
        return list(values)
    output, index = [], 0
    while index < len(values):
        first = last = values[index]
        while index + 1 < len(values) and values[index + 1] == last + 1:
            index += 1
            last += 1
        output.append([first, last] if last - first >= 2 else first)
        if last - first == 1:
            output.append(last)
        index += 1
    return output


def encodeHeader(header, inheritedEventCount):
    assertReleasedV2Header(header)
    cut = sessionFormatCount(inheritedEventCount, 'format v2 inherited event count')
    if not header['isSeeded'] and cut != 0:
        raise SessionFormatError('unseeded format v2 Session has inherited events')
    return dict(type='session', **{key: value for key, value in header.items() if value is not UNDEFINED})


def encodeEvent(event):
    if event.get('sourceEventSeqs', UNDEFINED) is UNDEFINED:
        return event
    return dict(event, sourceEventSeqs=encodeSeqRanges(event['sourceEventSeqs']))


class ReleasedV2Decoder:
    def __init__(self, value, recovery):
        self.header = decodePhysicalHeader(value)
        self._recovery = recovery
        self._rowIndex, self._eventCount, self._issue = 0, 0, None
        self._inherited = UNDEFINED

    def decodeRow(self, value, context):
        index = self._rowIndex
        self._rowIndex += 1
        try:
            event = decodeEvent(value, index)
        except Exception as error:
            current = error
            if not isinstance(current, SessionFormatError):
                current = SessionFormatError('released v2 row %s is malformed' % index)
                current.cause = error
            if self._recovery == 'strict':
                raise current
            self._issue = self._issue or current
            return
        if self._issue is not None:
            if event['type'] == 'turn/end':
                raise self._issue
            return
        seq = event['seq']
        if type(seq) not in (int, float) or seq != self._eventCount:
            gap = SessionFormatError('released v2 row %s has seq gap (expected %s, got %s)' % (
                index, self._eventCount, js_to_string(seq)))
            if self._recovery == 'strict':
                raise gap
            self._issue = gap
            if event['type'] == 'turn/end':
                raise gap
            return
        self._eventCount += 1
        if event['type'] == 'session/end-seed':
            data = record(event['data'], 'session/end-seed %s data' % js_to_string(seq))
            if data.get('inherited') is True:
                self._inherited = seq
        context.emitEvent(event)

    def finish(self, context):
        if self.header['isSeeded'] and self._inherited is UNDEFINED:
            raise SessionFormatError('released v2 seeded Session lacks an inherited end-seed marker')
        if not self.header['isSeeded'] and self._inherited is not UNDEFINED:
            raise SessionFormatError('released v2 unseeded Session contains an inherited end-seed marker')
        return 0 if self._inherited is UNDEFINED else self._inherited


releasedV2SessionFormatCodec = FrozenDict(version=2, decodeHeader=decodePhysicalHeader,
    createDecoder=ReleasedV2Decoder, encodeHeader=encodeHeader, encodeEvent=encodeEvent)
