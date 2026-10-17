"""Generation watermark fold and actual current Session/extension transactions."""
import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import patch

from dsh.cordis.context import Context
from dsh.core.abort import AbortSignal
from dsh.core.session.json import UNDEFINED
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.llm.deepseek_api_extensions import DeepSeekLlmApiExtensionRegistry
from dsh.session.session_log_deepseek_current import CurrentSessionLogDeepSeekPlugin, accepted_through


def execute(test, decode):
    async def run():
        results = []
        if test.get('operation') == 'fold':
            class Session: pass
            session = Session()
            session.id, session.header = 'upload', SimpleNamespace(version=test.get('version', 3))
            events = decode(test['events'])
            session.seq, session.eventAt = len(events), lambda i: events[i] if events[i] is not None else UNDEFINED
            try: return dict(value=accepted_through(session))
            except ValueError as error: return dict(error=str(error))
        ctx = Context()
        await ctx.plugin(CurrentSessionPlugin)
        await ctx.plugin(DeepSeekLlmApiExtensionRegistry)
        fiber = await ctx.plugin(CurrentSessionLogDeepSeekPlugin, dict(enabled=test.get('enabled', True)))
        options = dict(meta=test.get('meta', {}))
        if 'seed' in test: options['seed'] = test['seed']
        if 'cut' in test: options['inheritedEventCount'] = test['cut']
        session = ctx.get('sessions').create('upload', options)
        prepared = []
        try:
            for action in test['actions']:
                kind = action['op']
                if kind == 'append':
                    args = {}
                    if 'surfaceOp' in action: args['surface_op'] = action['surfaceOp']
                    if 'sourceEventSeqs' in action: args['source_event_seqs'] = action['sourceEventSeqs']
                    session.append(action['type'], action['data'], **args)
                elif kind == 'prepare':
                    request = dict(body=dict(messages=[dict(role='user', content='hello')]), signal=AbortSignal())
                    if not action.get('direct'): request['sessionId'] = action.get('sessionId', session.id)
                    result = await ctx.get('deepseekLlmApiExtensions').prepare(request)
                    prepared.append(result)
                    results.append(json.loads(json.dumps(result.fields)))
                elif kind == 'accept': await prepared[action.get('index', -1)].accept()
                elif kind == 'unload': await fiber.dispose()
            return dict(results=results, events=session.snapshotEvents())
        finally: await ctx.fiber.dispose()
    with patch('time.time', return_value=1): return asyncio.run(run())
