"""Explicit-Agent file references and cold-readable current skill metadata."""
from dsh.api.session_catalogs import SessionFileReferences
from dsh.api.session_commands_current import error_text
from dsh.api.settings import settled
from dsh.session.session_query import SessionQueryError
from dsh.typert.remote import Remote, RemoteError, TypertRemoteService


class CurrentSessionSkillCatalog(TypertRemoteService):
    inject = ['agents', 'sessionQuery', 'typert']

    def __init__(self, ctx):
        super().__init__(ctx, 'sessionSkillCatalog', dict(namespace='skills'))

    async def scope_for(self, sid, preset):
        live = self.ctx.get('agents').get(sid)
        if live is not None:
            return live
        presets = self.ctx.get('agentPresets')
        if presets is None:
            return None
        try:
            return await presets.standingKeyFor(preset)
        except Exception:
            return None

    @Remote
    async def list(self, request, signal):
        sid = request['sessionId']
        try:
            observation = await self.ctx.get('sessionQuery').observeSession(sid)
            try:
                if observation.projections is None:
                    raise RuntimeError('skill catalog requires a projected Session observation')
                cwd, preset = observation.header.cwd, observation.projections['values'].get('agentPreset')
            finally:
                observation.dispose()
        except SessionQueryError as error:
            if error.code == 'SESSION_QUERY_SESSION_NOT_FOUND':
                raise RemoteError('session/not-found', 'session "{}" not found'.format(sid), dict(sessionId=sid)) from None
            raise RemoteError('gateway/internal', 'session "{}" could not be inspected: {}'.format(sid, error_text(error)), {}) from None
        except Exception as error:
            raise RemoteError('gateway/internal', 'session "{}" could not be inspected: {}'.format(sid, error_text(error)), {}) from None
        if cwd is None:
            raise RemoteError('gateway/internal', 'session "{}" has no project cwd'.format(sid), {})
        live, presets = self.ctx.get('agents').get(sid), self.ctx.get('agentPresets')
        scoped = presets.serviceFor(live, 'skills') if live is not None and presets is not None else None
        registry = scoped if scoped is not None else self.ctx.get('skills')
        if registry is None:
            raise RemoteError('gateway/internal', "skill registry is absent: neither this session's agent preset nor the host composition mounts @deepseek-ai/dsh-skill", {})
        scope = await self.scope_for(sid, preset)
        try:
            skills = await settled(registry.list(dict(cwd=cwd, scope=scope)))
            return dict(skills=[dict({key: row[key] for key in ('name', 'description', 'whenToUse') if key in row},
                modelInvocable=row['invocation']['modelInvocable']) for row in skills if row['invocation']['userInvocable']])
        except Exception as error:
            raise RemoteError('gateway/internal', 'skill listing failed: ' + error_text(error), {}) from None
