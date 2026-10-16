"""rc.3 delegation definitions sampled for an unpublished or standing Session."""
import asyncio
import weakref

from dsh.core.scope import scope_of, scope_chain_of
from dsh.core.session.json import UNDEFINED
from dsh.subagent.canonical_tools import CanonicalToolSubagent
from dsh.subagent.composition_current import assert_max_depth
from dsh.subagent.model_selection_current import POLICY, read_policy, record_policy


class CurrentToolSubagent(CanonicalToolSubagent):
    inject = CanonicalToolSubagent.inject + ['sessionProjections']

    def _max_depth(self, config):
        if 'maxDepth' not in config:
            return 'provider-managed'
        if config['maxDepth'] != 'provider-managed':
            assert_max_depth(config['maxDepth'])
        return config['maxDepth']

    def _install_selected(self, ctx, install):
        projections = ctx.get('sessionProjections')
        projections.register(POLICY)
        if self.config.get('modelSelectionSettings') is not True:
            install(ctx, None)
            return
        settings = ctx.get('subagentModelSelection')
        if settings is None:
            raise ValueError('tool-subagent: `modelSelectionSettings` requires '
                             '@deepseek-ai/dsh-tool-subagent/model-selection-settings in the Host scope')

        def select(session):
            first = session.eventAt(0)
            fresh = session.firstLiveSeq == 0 and (first is UNDEFINED or first['type'] != 'session/end-seed')
            allowed = read_policy(projections, session)
            if allowed is None:
                parent_id = session.header.parentSession if session.header.origin == 'subagent' else None
                if parent_id is not None:
                    sessions = ctx.get('sessions')
                    if sessions is None:
                        raise ValueError('tool-subagent: child model-selection inheritance requires the Session registry')
                    parent = sessions.get(parent_id)
                    allowed = read_policy(projections, parent) if parent is not None else None
                elif fresh:
                    current = settings.current()
                    allowed = current['allowedModels'] if current['enabled'] else None
            if allowed is not None:
                record_policy(projections, session, allowed)
            return allowed

        session = getattr(self, '_session', None)
        if session is not None:
            install(ctx, select(session))
            return
        composition_scope = scope_of(ctx)
        if composition_scope is None:
            raise ValueError('tool-subagent: standing `modelSelectionSettings` requires a scoped preset Context')
        agents = ctx.get('agents')
        if agents is None:
            raise ValueError('tool-subagent: standing `modelSelectionSettings` requires the Agent registry')
        installed, installing = weakref.WeakKeyDictionary(), weakref.WeakSet()

        def admit(agent):
            if agent in installed or agent in installing:
                return
            installing.add(agent)
            try:
                policy = select(agent.session)
                installed[agent] = agent.ctx.inject(self.inject[:3], lambda runtime_ctx: install(runtime_ctx, policy))
            finally:
                installing.discard(agent)

        def remove(agent):
            fiber = installed.pop(agent, None)
            if fiber is not None:
                job = asyncio.create_task(fiber.dispose())
                def report(task):
                    if not task.cancelled() and task.exception() is not None:
                        ctx.logger.warn('tool-subagent: failed to remove recomposed Agent "%s" definitions: %s' % (agent.id, task.exception()))
                job.add_done_callback(report)

        def reconcile(*_):
            for agent in agents.list():
                if composition_scope in scope_chain_of(scope_of(agent.ctx)):
                    admit(agent)
                else:
                    remove(agent)
        ctx.on('agent/created', lambda payload: admit(payload['agent']))
        ctx.on('agent/disposed', lambda payload: remove(payload['agent']))
        ctx.on('tools/change', reconcile)
        reconcile()

        async def cleanup():
            fibers = list(installed.values())
            installed.clear()
            await asyncio.gather(*(fiber.dispose() for fiber in fibers))
        ctx.effect(lambda: cleanup, 'subagent model selection scopes')


def apply_tool_subagent(ctx, config, session=None):
    """Direct setup entry; the loader supplies its schema defaults separately."""
    plugin = CurrentToolSubagent(config)
    plugin._session = session
    return plugin.apply(ctx)
