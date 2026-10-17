"""Current generation upload DTOs and a real Agent/HTTP/storage transaction."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from dsh.core.session.current_session import CurrentSession
from dsh.llm.deepseek_api_extensions import DeepSeekLlmApiExtensionRegistry
from dsh.llm.llm_deepseek import LLMDeepSeekPlugin
from dsh.session.session_log_deepseek_current import CurrentSessionLogDeepSeekPlugin, accepted_through
from scripts.oracles.session_log_current_python import execute
from scripts.oracles.session_format_python import decode
from tests.test_agent_machine_current import mount, message


CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/session_log_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_upload_contract(case):
    result = execute(case, decode)
    assert result == case['expected']
    if case['case'] == 'session-log/assistant-stream':
        payload = result['results'][0]['dsh_session_log']
        assert payload['sessionFormatVersion'] == 3
        assert payload['events'][-1]['data']['stream'][0]['texts'] == ['ans', 'wer']
    if case['case'] == 'session-log/system-replace':
        assert result['results'][0]['dsh_session_log']['events'][-1]['sourceEventSeqs'] == [0]


@pytest.mark.asyncio
async def test_real_agent_http_2xx_commits_current_generation_watermark_and_reopens(tmp_path, monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-only')
    captured = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers['Content-Length'])).decode('utf-8')))
            raw = ('data: ' + json.dumps(dict(choices=[dict(delta=dict(content='answer'), finish_reason='stop')],
                usage=dict(prompt_tokens=3, completion_tokens=1, total_tokens=4))) + '\n\ndata: [DONE]\n\n').encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
    ctx = await mount(tmp_path)
    handle = None
    try:
        await ctx.plugin(DeepSeekLlmApiExtensionRegistry)
        await ctx.plugin(CurrentSessionLogDeepSeekPlugin, dict(enabled=True))
        await ctx.plugin(LLMDeepSeekPlugin, dict(baseURL='http://127.0.0.1:%s' % server.server_port,
            models=[dict(id='test')], streamIdleTimeoutMs=2000))
        handle = await ctx.get('agents').create(dict(sessionId='wire', options=dict(provider='deepseek-official', model='test')))
        agent = handle.agent
        for identity in ('first', 'second'):
            agent.followup(message(identity));await asyncio.wait_for(agent.whenIdle(), 5)
            assert agent.session.events[-1]['data']['reason']['kind'] == 'completed', agent.session.events[-1]
        assert len(captured) == 2
        first, second = [body['dsh_session_log'] for body in captured]
        assert first['sessionFormatVersion'] == second['sessionFormatVersion'] == 3
        assert first['afterSeq'] == -1 and second['afterSeq'] == first['throughSeq']
        assert len(first['events']) == first['throughSeq'] + 1
        assert second['events'][0]['seq'] == first['throughSeq'] + 1
        assert any(event['type'] == 'assistant/message' and event['data']['stream'] for event in second['events'])
        accepted = [event for event in agent.session.events if event['type'] == 'session-log-deepseek/delivery-accepted']
        assert len(accepted) == 2 and all(event['data']['sessionFormatVersion'] == 3 for event in accepted)
        assert accepted_through(agent.session) == second['throughSeq']
        await handle.dispose()
        reader = await ctx.get('sessionPersistence').open('wire', 'read')
        try:
            events = (await reader.read())['events']
            restored = CurrentSession.fromRestore('wire', events, reader.header, reader.inheritedEventCount)
            assert accepted_through(restored) == second['throughSeq']
        finally:
            await reader.close()
    finally:
        if handle: await handle.dispose()
        await ctx.fiber.dispose()
        server.shutdown();server.server_close();thread.join(2)
