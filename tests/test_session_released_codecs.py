"""Physical legacy formats are intentionally separate from logical restore policy."""
import json
from pathlib import Path

import pytest

from dsh.session.format import SessionFormatError, SessionFormatEventCollector
from dsh.session.format_v0_to_v1 import releasedV1SessionFormatCodec
from dsh.session.format_v1_to_v2 import releasedV2SessionFormatCodec
from scripts.oracles.session_format_python import observe

CORPUS = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_released_codec_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CORPUS, ids=[case['case'] for case in CORPUS])
def test_released_framing_admission_and_recovery(case):
    actual = observe(case)
    assert actual['outcome'] == case['expected']['outcome'], actual
    if 'name' in case['expected']:
        assert actual['name'] == case['expected']['name'], actual


def test_packed_run_can_be_consumed_lazily_or_expanded_repeatedly():
    decoder = releasedV1SessionFormatCodec['createDecoder'](dict(type='session', version=1,
        id='packed', createdAt=1, delegationDepth=0), 'strict')
    runs = []
    class Context:
        def emitRun(self, run):
            runs.append(run)
        def emitEvent(self, event):
            pytest.fail('Packed row must remain a compact run at the codec boundary')
    decoder.decodeRow(dict(type='tool-call-chunks', seq0=0, time0=10,
        data=dict(turn=1, step=2, index=3, id='call', name='read', dt=[2, -1], args=['{', '"a":1', '}'])), Context())
    run = runs[0]
    assert (run['firstSeq'], run['eventCount'], run['lastSeq'], run['lastTime']) == (0, 3, 2, 11)
    first = run['expand']()
    assert iter(first) is first
    events = list(first)
    assert events == list(run['expand']())
    assert [event['time'] for event in events] == [10, 12, 11]
    assert [event['data']['chunk']['argumentsDelta'] for event in events] == ['{', '"a":1', '}']


def test_seeded_zero_is_retained_and_v2_cut_is_discovered_from_body():
    physical = dict(type='session', version=1, id='seeded', createdAt=1, delegationDepth=0, seedLength=0)
    assert releasedV1SessionFormatCodec['decodeHeader'](physical)['isSeeded'] is True
    physical = dict(type='session', version=2, id='seeded', createdAt=1, delegationDepth=0, isSeeded=True)
    decoder = releasedV2SessionFormatCodec['createDecoder'](physical, 'strict')
    assert not hasattr(decoder, 'headerInheritedEventCount')
    events = SessionFormatEventCollector()
    decoder.decodeRow(dict(type='external/opaque', seq=0, time=1, data={}), events)
    decoder.decodeRow(dict(type='session/end-seed', seq=1, time=2, data=dict(inherited=True)), events)
    assert decoder.finish(events) == 1


def test_recoverable_scan_does_not_cross_corruption_into_a_closed_turn():
    decoder = releasedV2SessionFormatCodec['createDecoder'](dict(type='session', version=2,
        id='recovery', createdAt=1, delegationDepth=0, isSeeded=False), 'recoverable')
    events = SessionFormatEventCollector()
    decoder.decodeRow(dict(type='external/opaque', seq=0, time=1, data={}), events)
    decoder.decodeRow(None, events)
    decoder.decodeRow(dict(type='external/opaque', seq=1, time=2, data={}), events)
    assert len(events.values) == 1
    assert decoder.finish(events) == 0
    with pytest.raises(SessionFormatError, match='row 1 must be an object'):
        decoder.decodeRow(dict(type='turn/end', seq=1, time=3, data={}), events)


def test_physical_v2_roundtrip_preserves_nonmonotonic_provenance():
    codec = releasedV2SessionFormatCodec
    source = [4, 5, 1, 2, 3]
    event = dict(type='user/message', seq=6, time=7, data={}, surfaceOp='append', sourceEventSeqs=source)
    row = codec['encodeEvent'](event)
    assert row['sourceEventSeqs'] == source
    assert row['sourceEventSeqs'] is not source
    assert source == [4, 5, 1, 2, 3]
