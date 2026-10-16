"""Current list/search and actual cache reader with controlled synchronous medium."""
import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import patch

from dsh.api.session_list_current import CurrentSessionList
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.core.session.types import validate_session_header
from dsh.session.projections import SessionProjectionsPlugin
from dsh.session.projection_cache_current import CurrentSessionProjectionCache
from dsh.session.session_query import SessionQueryError


async def run(case):
    ctx, controller = Context(), AbortController()
    headers, sessions, calls, results, writes = {}, {}, [], [], []
    records = copy.deepcopy(case.get('records', {}))
    clock = patch.object(CurrentSession, '_event_time', return_value=1000)
    clock.start()
    try:
        await ctx.plugin(CurrentSessionPlugin)
        await ctx.plugin(SessionProjectionsPlugin)
        registry = ctx.get('sessionProjections')
        def title_schema(value):
            if value is not None and not isinstance(value, str):
                raise ValueError('invalid title')
            return value
        registry.register(dict(key='title', stateVersion=1, stateSchema=title_schema, init=lambda *_: None,
            apply=lambda state, event: event['data']['title'] if event['type'] == 'session/title' else state,
            wire=dict(viewSchema=title_schema, view=lambda value: value)))
        async def put(sid, record):
            writes.append(copy.deepcopy(record)); records[sid] = record
        cache = CurrentSessionProjectionCache(ctx, SimpleNamespace(get=records.get, put=put), dict(writeEveryEvents=100, writeIntervalMs=60000))
        ctx.set_service('sessionProjectionCache', cache)
        ctx.set_service('agents', SimpleNamespace(get=lambda sid: SimpleNamespace(status='running') if sid in case.get('running', []) else None))
        for record in case.get('headers', [dict(id='one', cwd='/project')]):
            meta = dict(dict(version=3, createdAt=100, isSeeded=False), **record)
            headers[meta['id']] = validate_session_header(meta['id'], meta, expected_version=3)
        async def list_sessions(signal=None):
            if case.get('listError'):
                raise RuntimeError('list failed')
            return [dict(header=header) for header in headers.values()]
        async def search(request, options):
            calls.append(copy.deepcopy(request))
            if options['signal'] is not controller.signal:
                raise RuntimeError('signal identity lost')
            page = case.get('pages', [{}])[min(len(calls) - 1, len(case.get('pages', [{}])) - 1)]
            if page.get('abort'):
                controller.abort(RuntimeError('cancelled'))
            if 'error' in page:
                raise SessionQueryError(page.get('message', 'provider refused'), page['error'])
            hits = []
            for item in page.get('items', []):
                hit = dict(header=headers.get(item['id'], SimpleNamespace(id=item['id'])), bestMatch=dict(sessionId=item.get('matchId', item['id']),
                    surface=item.get('surface', 'current'), type=item.get('type', 'user/message'), snippet=item.get('snippet', 'match')))
                hits.append(hit)
            return dict(items=hits, **(dict(nextCursor=page['nextCursor']) if 'nextCursor' in page else {}))
        if not case.get('noProvider'):
            ctx.set_service('sessionQuery', SimpleNamespace(listSessions=list_sessions, searchSessions=search))
        listing = CurrentSessionList(ctx)
        for sid in case.get('live', []):
            sessions[sid] = ctx.get('sessions').create(sid, dict(meta=headers[sid].to_dict()))
        for action in case['actions']:
            try:
                op = action['op']; sid = action.get('id', 'one')
                if op == 'list':
                    value = await listing.list(controller.signal)
                elif op == 'search':
                    value = await listing.search(action['query'], controller.signal)
                elif op == 'append':
                    for event in action['events']:
                        sessions[sid].append(event['type'], event['data'])
                    value = True
                elif op == 'snapshot':
                    value = registry.snapshot(sessions[sid])
                elif op == 'cached':
                    value = cache.cachedSnapshot(headers[sid], action.get('cut', 0))
                elif op == 'predecessor':
                    value = cache.cachedPredecessorTitle(headers[sid], action.get('cut', 0))
                elif op == 'cold':
                    value = cache.coldSnapshot(headers[sid], action.get('cut', 0), action.get('events', [])); await cache.drain()
                elif op == 'write':
                    await cache.write(sessions[sid]); value = True
                else:
                    raise ValueError('unknown list action')
                results.append(dict(outcome='value', value=value))
            except Exception as error:
                results.append(dict(outcome='error', error=dict(name=getattr(error, 'name', 'Error'), message=getattr(error, 'message', str(error)),
                    **(dict(code=error.code, details=error.details) if hasattr(error, 'details') else {}))))
        return dict(results=results, calls=calls, writes=writes)
    finally:
        await ctx.fiber.dispose()
        clock.stop()


def execute(case):
    return asyncio.run(run(case))
