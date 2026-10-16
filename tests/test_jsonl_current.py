"""Canonical generation framing and recovery before committed-prefix publication."""
import json
from pathlib import Path

import pytest

from dsh.session.jsonl_current import SessionLogScanner, header_bytes, scanLog
from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

CASES = json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/jsonl_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=[case['case'] for case in CASES])
def test_source_jsonl_current_observation(case):
    assert json_equal(json.loads(json.dumps(observe(case))), dict(case['expected'], case=case['case']))


def test_reused_decoder_buffer_does_not_change_fragment():
    header = header_bytes(dict(version=3,id='reuse',createdAt=1,isSeeded=False))
    event = dict(type='user/message',seq=0,time=1,surfaceOp='append',data=dict(id='question',role='user',source=dict(kind='user'),content=[dict(type='text',text='你好')]))
    body = (json.dumps(event,ensure_ascii=False)+'\n').encode('utf-8')
    split = body.index('你'.encode('utf-8'))+1
    reused = bytearray(body[:split])
    scanner = SessionLogScanner(header)
    scanner.write(reused)
    reused[:] = b'\x00'*len(reused)
    scanner.write(body[split:])
    assert scanner.finish() == scanLog(header+body)
