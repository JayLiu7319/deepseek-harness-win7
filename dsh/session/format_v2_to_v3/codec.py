"""V3 framing: structural admission precedes recoverable-tail processing."""
from dsh.core.session.json import UNDEFINED, FrozenDict
from dsh.cordis.utils import _js_strict_equal
from dsh.session.format import SessionFormatError, snapshotSessionFormatJson
from dsh.session.format.chain import call
from dsh.session.format_v1_to_v2 import releasedV2SessionFormatCodec
from .payload import assertV3StructuralRow, assertV3Event
from .validation import assertReleasedV3Header, assertV3EventAdmission


def v2_physical_header(value):
    header = snapshotSessionFormatJson(value, 'format v3 physical header')
    if not isinstance(header, dict) or not _js_strict_equal(header.get('version', UNDEFINED), 3):
        raise SessionFormatError('expected format v3 physical Session header')
    return dict(header, version=2)


def decodeHeader(value):
    return dict(call(releasedV2SessionFormatCodec, 'decodeHeader', v2_physical_header(value)), version=3)


def assertV3RowAdmission(row):
    assertV3StructuralRow(row)
    if isinstance(row, dict):
        assertV3EventAdmission(row)


class ReleasedV3Decoder:
    def __init__(self, value, recovery):
        self.decoder = call(releasedV2SessionFormatCodec, 'createDecoder', v2_physical_header(value), recovery)
        self.header = dict(self.decoder.header, version=3)
        self.recovery, self.issue, self.accepted_cut = recovery, None, UNDEFINED

    def decodeRow(self, row, context):
        assertV3RowAdmission(row)

        def emit_event(event):
            assertV3EventAdmission(event)
            if self.issue is None:
                try:
                    assertV3Event(event)
                except Exception as invalid:
                    if self.recovery == 'strict':
                        raise
                    self.issue = invalid
            if self.issue is not None:
                if event['type'] == 'turn/end':
                    raise self.issue
                return
            if event['type'] == 'session/end-seed' and isinstance(event['data'], dict) and event['data'].get('inherited') is True:
                self.accepted_cut = event['seq']
            call(context, 'emitEvent', event)

        class Proxy:
            emitEvent = staticmethod(emit_event)

            @staticmethod
            def emitRun(run):
                call(context, 'emitRun', run)

        self.decoder.decodeRow(row, Proxy())

    def finish(self, context):
        if self.issue is None:
            return self.decoder.finish(context)
        if self.decoder.header['isSeeded'] and self.accepted_cut is UNDEFINED:
            raise SessionFormatError('format v3 seeded Session lacks an accepted inherited end-seed marker')
        if not self.decoder.header['isSeeded'] and self.accepted_cut is not UNDEFINED:
            raise SessionFormatError('format v3 unseeded Session contains an inherited end-seed marker')
        return 0 if self.accepted_cut is UNDEFINED else self.accepted_cut


def encodeHeader(header, inheritedEventCount):
    assertReleasedV3Header(header)
    return dict(call(releasedV2SessionFormatCodec, 'encodeHeader', dict(header, version=2), inheritedEventCount), version=3)


def encodeEvent(event):
    assertV3EventAdmission(event)
    assertV3Event(event)
    return call(releasedV2SessionFormatCodec, 'encodeEvent', event)


releasedV3SessionFormatCodec = FrozenDict(version=3, decodeHeader=decodeHeader,
    createDecoder=ReleasedV3Decoder, encodeHeader=encodeHeader, encodeEvent=encodeEvent)
