"""Compact attempt consumers must agree with the canonical LLM stream contract."""
import json
from pathlib import Path

import pytest

from dsh.core.session.json import UNDEFINED
from dsh.llm.assistant_stream import (AssistantStreamAccumulator, expandAssistantStream,
    assistantStreamFirstTokenTime, assistantStreamHasVisibleContent, assistantStreamHasVisibleText,
    runFirstTokenTime, runFirstVisibleTime)
from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/assistant_stream_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=[case['case'] for case in CASES])
def test_canonical_stream_source_observation(case):
    assert json_equal(json.loads(json.dumps(observe(case))), dict(case['expected'], case=case['case']))


def test_accumulator_detaches_input_and_prior_snapshots():
    accumulator = AssistantStreamAccumulator()
    chunk = dict(type='text-delta', index=0, text='a')
    timed = accumulator.push(dict(time=1, chunk=chunk))
    first = accumulator.snapshot()
    chunk['text'] = 'changed'
    accumulator.push(dict(time=2, chunk=dict(type='text-delta', index=0, text='b')))
    assert timed['chunk']['text'] == 'a'
    assert [value['chunk']['text'] for value in expandAssistantStream(first)] == ['a']
    assert [value['chunk']['text'] for value in expandAssistantStream(accumulator.snapshot())] == ['a', 'b']
    with pytest.raises(TypeError):
        first[0]['texts'].append('mutated')


def test_durable_raw_chunk_expansion_detaches_input():
    chunk = dict(type='usage', usage=dict(inputTokens=1, outputTokens=2))
    expanded = expandAssistantStream([dict(type='chunk', time=1, chunk=chunk)])
    chunk['usage']['inputTokens'] = 999
    assert expanded[0]['chunk']['usage']['inputTokens'] == 1


def test_readers_stop_without_reaching_later_records():
    class FailOnRead(dict):
        def __getitem__(self, key):
            pytest.fail('Reader accessed records beyond the first qualifying member')
    stream = [dict(type='text-chunks', time0=1, index=0, dt=[1], texts=['yes', 'later']), FailOnRead()]
    assert assistantStreamFirstTokenTime(stream) == 1
    assert assistantStreamHasVisibleContent(stream) is True
    assert assistantStreamHasVisibleText(stream) is True


def test_packed_member_scan_stops_at_first_matching_fragment():
    class Fragments(list):
        def __iter__(self):
            yield self[0]
            pytest.fail('Packed run scanned past its first qualifying member')
    run = dict(type='text-chunks', time0=1, index=0, dt=[1], texts=Fragments(['yes', 'later']))
    assert runFirstTokenTime(run) == 1
    assert runFirstVisibleTime(run) == 1
    assert runFirstVisibleTime(dict(type='tool-call-chunks', time0=1, args=['x'])) is UNDEFINED
