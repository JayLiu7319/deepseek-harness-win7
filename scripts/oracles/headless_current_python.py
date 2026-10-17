"""Actual current runner with deterministic drive and independently scripted frames/log."""
import asyncio
import copy
import io
from types import SimpleNamespace
from unittest.mock import patch

from dsh.cordis.context import Context
from dsh.boot.profile_boot import _AppReadyService
from dsh.bundle.headless.current import CurrentHeadlessRunner
from dsh.core.session.json import UNDEFINED


def execute(test):
    async def run():
        ctx, out, err = Context(), io.StringIO(), io.StringIO()
        done = asyncio.get_running_loop().create_future()
        order, options, events = [], [], []
        session = SimpleNamespace(id='owned', events=events, seq=0,
            eventAt=lambda i: UNDEFINED if i == test.get('missing') else events[i])
        async def idle(): pass
        def followup(message):
            assert message['id'] and message['role'] == 'user'
            order.append('prompt')
            for entry in test['frames']:
                ctx.emit('agent/assistant-stream', dict(agent=object() if entry.get('foreign') else agent, frame=entry['frame']))
            for i, event in enumerate(copy.deepcopy(test['events'])):
                events.append(dict(event, seq=i));session.seq += 1
        agent = SimpleNamespace(session=session, followup=followup, when_idle=idle)
        async def create(request):
            options.append(request['agentOptions'])
            return SimpleNamespace(agent=agent)
        async def flush(subject):
            assert subject is session;order.append('flush')
        def exit(code): order.append('exit');done.set_result(code)
        ready = _AppReadyService()
        ctx.set_service('agentDefaultModel', SimpleNamespace(current_selection=lambda: dict(provider='mock', model='model', reasoningEffort='high')))
        ctx.set_service('agents', SimpleNamespace(create=create));ctx.set_service('sessions', SimpleNamespace(flush=flush))
        ctx.set_service('appExit', exit);ctx.set_service('appReady', ready)
        with patch('sys.stdout', out), patch('sys.stderr', err):
            try:
                await ctx.plugin(CurrentHeadlessRunner, dict(task=test.get('task', 'task')))
                ready._commit();code = await asyncio.wait_for(done, 2)
            finally: await ctx.fiber.dispose()
        return dict(code=code, out=out.getvalue(), err=err.getvalue(), order=order, options=options)
    return asyncio.run(run())
