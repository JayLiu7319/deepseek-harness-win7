"""Actual current history/control journals with explicit observations and Inbox."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from dsh.api.session_assistant_stream_current import SessionAssistantStreamAccumulator
from dsh.api.session_control_current import CurrentSessionControl
from dsh.api.session_history_current import CurrentSessionHistory
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.inbox_current import ReactLoopInbox
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.session.projections import SessionProjectionsPlugin
from dsh.session.session_query import SessionQueryError


async def run(case):
    if case.get('mode') == 'accumulator':
        accumulator, previous, results = SessionAssistantStreamAccumulator(), None, []
        for action in case['actions']:
            if action['op'] == 'frame':
                accumulator.accept(action['frame'], action.get('cursor', -1))
            else:
                value = accumulator.snapshot()
                results.append(dict(value=value, same=previous is value)); previous = value
        return dict(results=results)
    ctx, controller, live, results, calls, iterators, frames = Context(), AbortController(), {}, [], [], {}, {}
    counts, streams = dict(disposed=0, retained=0, promoted=0), {}
    clock = patch.object(CurrentSession, '_event_time', return_value=1000); clock.start()
    try:
        await ctx.plugin(CurrentSessionPlugin)
        await ctx.plugin(SessionProjectionsPlugin)
        ctx.set_service('agents', SimpleNamespace(get=live.get))
        meta = dict(dict(createdAt=100, cwd='/workspace'), **case.get('meta', {}))
        if meta.get('cwd') is None:
            meta.pop('cwd', None)
        session = ctx.get('sessions').create('one', dict(meta=meta))
        class Agent:
            pass
        agent = Agent(); agent.id, agent.session, agent.ctx = 'one', session, ctx
        live['one'] = agent
        agent.inbox = ReactLoopInbox(ctx.get('sessionProjections'), session, SimpleNamespace(emit=lambda *_: None))
        def apply(events):
            for event in events:
                session.append(event['type'], event['data'], **({'surface_op': event['surfaceOp']} if 'surfaceOp' in event else {}),
                    **({'source_event_seqs': event['sourceEventSeqs']} if 'sourceEventSeqs' in event else {}))
        apply(case.get('events', []))
        def dispose():
            counts['disposed'] += 1
        def retained():
            counts['retained'] += 1
            return SimpleNamespace(dispose=dispose)
        def observation():
            values = dict(case.get('projections', {}))
            return SimpleNamespace(header=session.header, events=session.snapshotEvents(), cursor=session.seq - 1,
                inheritedEventCount=case.get('cut', 0), projections=dict(asOfSeq=session.seq - 1, values=values),
                source=case.get('source', 'attached'), dispose=dispose, retain=retained)
        async def observe(sid, options):
            calls.append(dict(sessionId=sid, projectionMode=options['projectionMode'], signal=options['signal'] is controller.signal))
            if case.get('missing'):
                raise SessionQueryError('missing', 'SESSION_QUERY_SESSION_NOT_FOUND')
            for frame in case.get('openingFrames', []):
                ctx.emit('agent/assistant-stream', dict(agent=agent, frame=frame))
            return observation()
        ctx.set_service('sessionQuery', SimpleNamespace(observeSession=observe))
        def promote(observed):
            counts['promoted'] += 1
            observed.dispose()
            if case.get('promotionError'):
                raise RuntimeError('promotion rejected')
        history, control = CurrentSessionHistory(ctx, promote), CurrentSessionControl(ctx)
        jobs, callbacks = {}, []
        def subscribe(callback):
            callbacks.append(callback)
            def remove():
                callbacks.remove(callback)
            ctx.effect(lambda: remove)
            return remove
        ctx.set_service('jobs', SimpleNamespace(list=lambda owner: jobs.get(owner.id if owner is not None else '*', []), onJobsChanged=subscribe))
        address = case.get('address', dict(kind='session', sessionId='one'))
        async def next_value(iterator):
            try:
                return dict(done=False, value=await asyncio.wait_for(iterator.__anext__(), 2))
            except StopAsyncIteration:
                return dict(done=True)
        for action in case['actions']:
            try:
                op = action['op']
                if op == 'page':
                    value = await history.page(dict(address=address, **action.get('request', {})), controller.signal)
                elif op == 'follow':
                    iterator = history.follow(dict(address=address, **action.get('request', {})), controller.signal)
                    iterators['history'] = iterator; value = await next_value(iterator)
                elif op == 'control':
                    iterator = control.control(controller.signal); iterators['control'] = iterator; value = await next_value(iterator)
                elif op == 'next':
                    value = await next_value(iterators[action.get('stream', 'history')])
                elif op == 'append':
                    apply(action['events']); value = True
                elif op == 'frame':
                    ctx.emit('agent/assistant-stream', dict(agent=agent, frame=action['frame'])); value = True
                elif op == 'disposed':
                    ctx.emit('agent/disposed', dict(agent=agent)); value = True
                elif op == 'inbox':
                    agent.inbox.append(action.get('target', 'next-turn'), action['message']); value = True
                elif op == 'remove':
                    agent.inbox.remove(action['id']); value = True
                elif op == 'jobs':
                    owner = None if action.get('all') else agent
                    jobs[agent.id] = action['jobs']
                    for callback in callbacks:
                        callback(owner)
                    value = True
                elif op == 'close':
                    history.close(); control.close(); value = True
                elif op == 'abort':
                    controller.abort(); value = True
                else:
                    raise ValueError('unknown history operation')
                results.append(dict(outcome='value', value=value))
            except Exception as error:
                results.append(dict(outcome='error', error=dict(name=getattr(error, 'name', 'Error'), message=getattr(error, 'message', str(error)),
                    **(dict(code=error.code, details=error.details) if hasattr(error, 'details') else {}))))
        for iterator in iterators.values():
            await iterator.aclose()
        return dict(results=results, calls=calls, counts=counts)
    finally:
        await ctx.fiber.dispose(); clock.stop()


def execute(case):
    # Observe the JSON wire vocabulary, including frozen runtime containers.
    return json.loads(json.dumps(asyncio.run(run(case)), ensure_ascii=False))
