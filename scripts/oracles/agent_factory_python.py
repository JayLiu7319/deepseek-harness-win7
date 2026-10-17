"""Observation-only Python half of the source-derived Agent factory probes."""
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dsh.cordis import Context
from dsh.core.agent import AgentPlugin
from dsh.session.projections import SessionProjectionRegistry
from dsh.core.agent_loop_current import CurrentAgentLoopPlugin
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.abort import AbortController


async def main():
    rows = []
    for mode in ['success', 'reject', 'commit', 'caller-load', 'owner-load', 'factory-load',
                 'caller-setup', 'owner-setup', 'factory-setup']:
        ctx = Context()
        SessionProjectionRegistry(ctx)
        CurrentSessionPlugin().apply(ctx)
        AgentPlugin().apply(ctx)
        CurrentAgentLoopPlugin().apply(ctx)
        owner = ctx.plugin(lambda scope: None)
        await owner
        signal = AbortController()
        session = ctx.get('sessions').prepare('probe')
        reached, late, released = asyncio.Event(), asyncio.Event(), asyncio.Event()
        counters = {'releases': 0, 'committed': 0}
        setup_session = []
        events = []
        for name in ['session/created', 'agent/created', 'agent/session-start']:
            ctx.on(name, lambda *args, name=name: events.append(name))
        async def release():
            counters['releases'] += 1
            released.set()
        async def read(*args, **kwargs):
            return dict(events=session.snapshotEvents(), eventState='shared-frozen')
        async def append(events):
            pass
        stored_handle = SimpleNamespace(header=session.header, inheritedEventCount=session.inheritedEventCount,
                                        read=read, append=append, close=release)
        async def open_handle(sid, ownership_mode, options=None):
            assert ownership_mode == 'write'
            if mode.endswith('-load'):
                reached.set()
                await late.wait()
            return stored_handle
        ctx.set_service('sessionPersistence', SimpleNamespace(open=open_handle))
        def commit():
            if mode == 'commit':
                raise RuntimeError('commit failed')
            counters['committed'] += 1
        async def setup(scope, agent):
            setup_session.append(agent.session)
            if not mode.endswith('-load'):
                reached.set()
                await late.wait()
            if mode == 'reject':
                raise RuntimeError('setup failed')
            return SimpleNamespace(commit=commit)
        job = asyncio.create_task(owner.ctx.get('agents').resume({
            'resumeSessionId': 'probe', 'signal': signal.signal, 'setup': setup}))
        entered = asyncio.create_task(reached.wait())
        done, _pending = await asyncio.wait((entered, job), timeout=5,
                                            return_when=asyncio.FIRST_COMPLETED)
        if entered not in done:
            entered.cancel()
            if job in done:
                await job
            raise RuntimeError('factory did not reach gated open/setup')
        before = {'session': ctx.get('sessions').get('probe') is not None,
                  'agent': ctx.get('agents').get('probe') is not None, 'events': list(events)}
        if mode.startswith('caller-'):
            signal.abort(RuntimeError('cancelled'))
        elif mode.startswith('owner-'):
            await owner.dispose()
        elif mode.startswith('factory-'):
            await ctx.get('agent_loop').teardown()
        else:
            late.set()
        handle = None
        try:
            handle = await job
        except RuntimeError:
            pass
        late.set()
        if handle is None:
            await asyncio.wait_for(released.wait(), 2)
        after = {'rejected': handle is None, 'exact': handle is not None and handle.agent.session is setup_session[0],
                 'events': list(events), **counters}
        if handle:
            await handle.dispose()
        clean = ctx.get('sessions').get('probe') is None and ctx.get('agents').get('probe') is None
        await ctx.fiber.dispose()
        rows.append({'mode': mode, 'before': before, 'after': after, 'clean': clean})
    Path(sys.argv[1]).write_text(json.dumps(rows, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
