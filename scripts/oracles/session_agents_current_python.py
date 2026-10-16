"""Current API Agent policy with real Sessions/projections and controlled factories."""
import asyncio
import tempfile
import re
from types import SimpleNamespace

from dsh.api.session_agents_current import CurrentSessionAgents, install_model_selection_projection, inspect_api_session
from dsh.cordis.context import Context
from dsh.core.scope import create_scope
from dsh.core.session.current_session import CurrentSessionPlugin
from dsh.core.session.types import validate_session_header
from dsh.session.projections import SessionProjectionsPlugin
from dsh.session.session_query import SessionQueryError
from dsh.typert.registry import TypertRegistry


async def run(case):
    ctx = Context()
    live, counts, results, cold = {}, dict(create=0, resume=0, observe=0, disposed=0, setup=0), [], case.get('cold')
    with tempfile.TemporaryDirectory(prefix='rc3-activation-') as cwd:
        ids, created, attached, saved = {}, [], [], []
        def normalize(value):
            if isinstance(value, str):
                def replace(match):
                    return ids.setdefault(match.group(), 'opaque:' + str(len(ids) + 1))
                return re.sub(r'session-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', replace, value.replace(cwd, '<cwd>'))
            if isinstance(value, (list, tuple)):
                return [normalize(item) for item in value]
            if isinstance(value, dict):
                return {key: normalize(item) for key, item in value.items()}
            return value
        def header(sid, meta=None):
            return dict(dict(version=3, id=sid, createdAt=1, isSeeded=False, cwd=cwd), **(meta or {}))
        async def make(sid, meta=None, request=None):
            class Agent:
                pass
            agent = Agent()
            agent.id, agent.status = sid, 'idle'
            options = dict(meta=header(sid, meta))
            options.update({key: request[key] for key in ('seed', 'inheritedEventCount') if key in (request or {})})
            agent.session = ctx.get('sessions').create(sid, options)
            agent.ctx = create_scope(ctx, agent).ctx
            live[sid] = agent
            return agent
        async def factory(request, kind):
            counts[kind] += 1
            await asyncio.sleep(0)
            if case.get('factoryError'):
                raise RuntimeError('factory failed')
            sid = request.get('sessionId', request.get('resumeSessionId'))
            meta = request.get('meta', cold or {})
            agent = await make(sid, meta, request)
            if case.get('commands'):
                created.append({key: request[key] for key in ('sessionId', 'resumeSessionId', 'seed', 'inheritedEventCount', 'meta', 'agentOptions') if key in request})
            if case.get('race'):
                if case['race'] == 'child':
                    # A child wins publication while the ordinary factory fails.
                    agent.session.header = validate_session_header(sid, header(sid, dict(meta, origin='subagent')), expected_version=3)
                raise RuntimeError('raced publication')
            if case.get('returnedCwd'):
                agent.session.header = validate_session_header(sid, header(sid, dict(cwd='/other')), expected_version=3)
            await request['setup'](agent.ctx, agent)
            counts['setup'] += 1
            return SimpleNamespace(agent=agent)
        def observation(sid):
            meta = header(sid, cold)
            if cold is not None and cold.get('cwd', '') is None:
                meta.pop('cwd', None)
            def dispose():
                counts['disposed'] += 1
            return SimpleNamespace(header=validate_session_header(sid, meta, expected_version=3), inheritedEventCount=0, events=case.get('events', []),
                projections=None if case.get('unprojected') else dict(values=dict(agentPreset=meta.get('agentPreset'))), dispose=dispose)
        async def observe(sid, options=None):
            counts['observe'] += 1
            if cold is None:
                raise SessionQueryError('missing', 'SESSION_QUERY_SESSION_NOT_FOUND')
            return observation(sid)
        try:
            for plugin in (CurrentSessionPlugin, SessionProjectionsPlugin, TypertRegistry):
                await ctx.plugin(plugin)
            ctx.get('sessionProjections').register(dict(key='agentPreset', stateVersion=1, stateSchema=lambda value: value,
                init=lambda header, _: header.agentPreset, apply=lambda state, _: state))
            install_model_selection_projection(ctx)
            ctx.set_service('agentDefaultModel', SimpleNamespace(currentSelection=lambda: dict(provider='fixture', model='model', reasoningEffort='default')))
            ctx.set_service('agents', SimpleNamespace(get=live.get, isOwnedBy=lambda *_: False,
                create=lambda request: factory(request, 'create'), resume=lambda request: factory(request, 'resume')))
            ctx.set_service('sessionQuery', SimpleNamespace(observeSession=observe))
            api = CurrentSessionAgents(ctx)
            if case.get('commands'):
                from dsh.api.session_commands_current import CurrentSessionCommands
                from dsh.session.canonical_title import SessionTitleService
                from dsh.typert.remote import RemoteError
                if not case.get('noTitle'):
                    await ctx.plugin(SessionTitleService, dict(fallbackMaxWords=5, fallbackMaxBytes=40, maxTitleBytes=80))
                async def save(value):
                    saved.append(value)
                    if case.get('saveError'):
                        raise RuntimeError('defaults write failed')
                ctx.get('agentDefaultModel').saveSelection = save
                async def config(value):
                    if case.get('modelError'):
                        if case['modelError'] == 'remote':
                            raise RemoteError('gateway/bad-request', 'bad route', {})
                        raise RuntimeError('model refused')
                    return dict(value, model=value['model'].strip())
                ctx.set_service('llm', SimpleNamespace(resolveCallConfig=config))
                async def attach(sid):
                    attached.append(sid)
                    if case.get('attachError'):
                        raise RuntimeError('workspace write failed')
                workspace = SimpleNamespace(id='workspace', path=cwd, sessionIds=case.get('workspaceSessions', []), attachSession=attach)
                ctx.set_service('workspaceRegistry', SimpleNamespace(get=lambda wid: workspace if wid == 'workspace' else None,
                    list=lambda: [workspace] if case.get('workspace') else []))
                async def trace(sid):
                    if case.get('traceError'):
                        raise RuntimeError('lineage unavailable')
                    return dict(ancestors=[dict(header=SimpleNamespace(id=sid)) for sid in case.get('ancestors', [])])
                ctx.get('sessionQuery').traceSession = trace
                controller = CurrentSessionCommands(ctx, api, cwd)
            if case.get('live') is not None:
                await make('one', case['live'])
            for action in case['actions']:
                try:
                    op = action['op']
                    if op == 'command':
                        request = dict(action.get('request', {}))
                        if action['name'] != 'create':
                            request.setdefault('sessionId', 'one')
                        value = await getattr(controller, action['name'])(request)
                    elif op == 'ensure':
                        values = await asyncio.gather(*(api.ensureSession('one', cwd, action.get('persisted', False), action.get('preset')) for _ in range(action.get('count', 1))), return_exceptions=True)
                        value = []
                        for item in values:
                            if isinstance(item, BaseException):
                                raise item
                            value.append(dict(id=item.id, cwd=item.session.header.cwd, preset=api.presetForSession(item.session)))
                    elif op in ('resolve', 'observed'):
                        found = await (api.resolveAgent('one') if op == 'resolve' else api.resolveObservedAgent(observation('one')))
                        if 'error' in found:
                            raise found['error']
                        value = dict(id=found['agent'].id)
                    elif op == 'inspect':
                        item = await inspect_api_session(ctx, 'one')
                        value = dict(id=item['meta'].id, events=item['events'], inheritedEventCount=item['inheritedEventCount'])
                    elif op == 'select':
                        api.selectForNextRequest(live['one'], action['value']); value = True
                    elif op == 'header':
                        live['one'].session.append('request/header', dict(reason='initial', header=action['value'])); value = True
                    elif op == 'selection':
                        value = api.selectionFor(live['one']).current.to_dict()
                    elif op == 'consume':
                        selected = action['value']; value = api.consumeSelection(live['one'], selected['provider'], selected['model'], selected.get('reasoningEffort'))
                    elif op == 'projection':
                        value = ctx.get('sessionProjections').stateOf(live['one'].session, 'modelSelection')
                    elif op == 'serial':
                        order = []
                        async def work(index):
                            order.append('enter' + str(index)); await asyncio.sleep(0); order.append('exit' + str(index))
                            if index == 0:
                                raise RuntimeError('first failed')
                            return index
                        settled = await asyncio.gather(*(api.serializeImageAdmission(live['one'], lambda index=index: work(index)) for index in range(3)), return_exceptions=True)
                        value = dict(order=order, settled=[str(item) if isinstance(item, BaseException) else item for item in settled])
                    else:
                        raise ValueError('unknown action ' + op)
                    results.append(dict(outcome='value', value=normalize(value)))
                except Exception as error:
                    results.append(dict(outcome='error', error=normalize(dict(name='RemoteError' if hasattr(error, 'details') else 'Error', message=str(error),
                        **(dict(code=error.code, details=error.details) if hasattr(error, 'details') else {})))))
            return dict(results=results, counts=counts, **(dict(created=normalize(created), attached=normalize(attached), saved=saved) if case.get('commands') else {}))
        finally:
            await ctx.fiber.dispose()


def execute(case):
    return asyncio.run(run(case))
