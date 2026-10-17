"""Current one-shot progress reads live frames; outcome stays on the durable log."""
import os
import sys
import uuid

from dsh.bundle.headless.runner import HeadlessRunnerPlugin
from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import js_to_string
from dsh.cordis.schema import Schema as z


def stream_reasoning(ctx, agent, stderr):
    line = dict(open=False, newline=True)
    def close():
        if line['open'] and not line['newline']:
            stderr.write('\n')
        line.update(open=False, newline=True)
    def observe(payload):
        if payload['agent'] is not agent:
            return
        frame = payload['frame']
        if frame['type'] in ('start', 'end'):
            close()
            return
        chunk = frame['chunk']
        kind = chunk['type']
        if kind == 'reasoning-delta':
            text = chunk['text']
            if not text:
                return
            if not line['open']:
                stderr.write('dsh: reasoning:\n')
            stderr.write(text)
            stderr.flush()
            line.update(open=True, newline=text.endswith('\n'))
        elif kind not in ('usage', 'block-start', 'block-end') or kind == 'block-start' and chunk['blockType'] != 'reasoning' or kind == 'block-end' and chunk['block']['type'] != 'reasoning':
            close()
    remove = ctx.on('agent/assistant-stream', observe)
    def dispose():
        remove()
        close()
    return dispose, close


def summarize(session, first_seq):
    started, text, reason = False, '', None
    length = session.seq
    for seq in range(int(first_seq), int(length)):
        event = session.eventAt(seq)
        if event is UNDEFINED:
            raise ValueError('headless summary cannot read seq %s below captured length %s' % (seq, js_to_string(length)))
        if event['type'] == 'turn/start':
            started = True
            continue
        if not started:
            continue
        if event['type'] == 'assistant/message':
            joined = ''.join(block['text'] for block in event['data']['message']['content'] if block['type'] == 'text')
            if joined:
                text = joined
        if event['type'] == 'turn/end':
            reason = event['data']['reason']
    return text, reason


class CurrentHeadlessRunner(HeadlessRunnerPlugin):
    Config = z.object(dict(task=z.string().required()))

    def validate_task(self, task):
        if not isinstance(task, str):
            raise ValueError('headless-runner requires a task')

    def stream_reasoning(self, ctx, agent):
        return stream_reasoning(ctx, agent, sys.stderr)

    def summarize(self, session, first_seq):
        return summarize(session, first_seq)

    async def create_agent(self, ctx, selected, setup):
        return await ctx.get('agents').create(dict(sessionId='session-' + str(uuid.uuid4()),
            agentOptions={key: selected[key] for key in ('provider', 'model')}, meta=dict(cwd=os.getcwd()), setup=setup))
