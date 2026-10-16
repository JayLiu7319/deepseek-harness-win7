"""Current goal providers using projection-owned replay and scoped Agent events."""
import copy
import re
import uuid

from dsh.cordis.text import trim_js
from dsh.core.agent_dispatch_current import emit_agent_event
from dsh.goal.driver import GoalRoundDriver
from dsh.goal.fold import empty_goal_state, goal_ref, integer
from dsh.goal.fold_current import DEFINITION
from dsh.goal.service import GoalService, GoalError, max_rounds
from dsh.goal.tools import CanonicalToolGoal, goal_value, render_wrapup, summary
from dsh.llm.error import HarnessError
from dsh.llm.message import create_user_message
from dsh.typert.remote import Remote


def objective(value):
    if not isinstance(value, str) or not trim_js(value):
        raise GoalError('goal objective must be a non-empty string', 'GOAL_INVALID_OBJECTIVE')
    return trim_js(value)


class CurrentGoalService(GoalService):
    inject = ['agents', 'sessionProjections']

    def __init__(self, ctx, config=None):
        config = dict(config or {})
        if config.get('defaultMaxGoalRounds') is None:
            config['defaultMaxGoalRounds'] = 256
        super().__init__(ctx, config)
        ctx.on('session/event', self._event)

    def _projection_definition(self):
        return DEFINITION

    def _cache(self, session):
        if session not in self.caches:
            self.caches[session] = dict(state=empty_goal_state(), activation='disarmed', observed=0, pending=None)
        return self.caches[session]

    def _projection(self, session):
        state = self.ctx.get('sessionProjections').stateOf(session, 'goal')
        if state is None:
            raise RuntimeError('goal projection is not registered')
        if state['failure'] is not None:
            raise RuntimeError(state['failure'])
        return state

    def _sync(self, session, cache):
        state = self._projection(session)
        folded = empty_goal_state()
        if state['current'] is not None:
            folded.update(copy.deepcopy(state['current']))
        folded['seenGoalIds'] = set(state['seenGoalIds'])
        cache.update(state=folded, observed=session.seq)

    def _set_activation(self, session, activation):
        cache = self._cache(session)
        if cache['activation'] == activation:
            return
        cache['activation'] = activation
        try:
            current = self._projection(session)['current']
        except Exception:
            return
        payload = dict(sessionId=session.id)
        if current is not None:
            payload['goal'] = dict(goal_ref(current['goal']), activation=activation)
        self.ctx.emit('goal/activation-changed', payload)

    def _event(self, session, event):
        if event['type'] == 'goal/change':
            pending = self._cache(session)['pending']
            self._set_activation(session, pending[1] if pending is not None and pending[0] == event['seq'] else 'disarmed')

    def _session_start(self, payload):
        self._set_activation(payload['agent'].session, 'disarmed')

    @Remote('get')
    def get(self, agent):
        return super().get(agent)

    def disarm(self, agent):
        if self.ctx.get('agents').get(agent.id) is not agent:
            raise GoalError('agent "{}" is not live in this registry'.format(agent.id), 'GOAL_AGENT_NOT_LIVE')
        self._set_activation(agent.session, 'disarmed')
        return self.get(agent)

    def _expect(self, cache, ref):
        current = cache['state']['goal']
        if current is None:
            raise GoalError('no current goal', 'GOAL_NOT_FOUND')
        if ref.get('id') != current['id'] or ref.get('revision') != current['revision']:
            raise GoalError('stale goal ref "{}" revision {}; current is "{}" revision {}'.format(
                ref.get('id'), ref.get('revision'), current['id'], current['revision']), 'GOAL_STALE_REVISION')
        return current

    def _commit(self, agent, cache, change, activation):
        ref = copy.deepcopy(change.get('cleared') or goal_ref(change['goal']))
        cache['pending'] = (agent.session.seq, activation)
        try:
            event = agent.session.append('goal/change', change)
            if event['seq'] == cache['pending'][0]:
                cache['activation'] = activation
        finally:
            cache['pending'] = None
        self._sync(agent.session, cache)
        view = self._view(cache)
        change = dict(operation=change['operation'], ref=ref)
        if view is not None:
            change['goal'] = view
        emit_agent_event(self.ctx, agent, 'goal/changed', dict(change=change))
        return view

    def create(self, agent, request):
        text = objective(request.get('objective'))
        rounds = request.get('maxGoalRounds')
        rounds = max_rounds(self.default_rounds if rounds is None else rounds)
        cache = self._prepare(agent)
        current = cache['state']['goal']
        if current is not None and current['phase'] != 'complete':
            raise GoalError('goal "{}" already exists with phase "{}"'.format(current['id'], current['phase']), 'GOAL_ALREADY_EXISTS')
        return self._snapshot(agent, cache, 'create', dict(id='goal-' + str(uuid.uuid4()), revision=1,
            objective=text, phase='active', maxGoalRounds=rounds), 'armed', new=True)

    @Remote('edit')
    def edit(self, agent, ref, request):
        cache = self._prepare(agent)
        goal = copy.deepcopy(self._expect(cache, ref))
        if not any(key in request for key in ('objective', 'maxGoalRounds')):
            raise GoalError('goal edit requires objective and/or maxGoalRounds', 'GOAL_INVALID_EDIT')
        goal['revision'] += 1
        if 'objective' in request:
            goal['objective'] = objective(request['objective'])
        if 'maxGoalRounds' in request:
            goal['maxGoalRounds'] = max_rounds(request['maxGoalRounds'])
        return self._snapshot(agent, cache, 'edit', goal, cache['activation'])

    def _transition(self, agent, ref, operation, allowed, phase, activation, reason=None):
        cache = self._prepare(agent)
        current = self._expect(cache, ref)
        if current['phase'] not in allowed:
            raise GoalError('cannot {} goal "{}" from phase "{}"; expected {}'.format(
                operation, current['id'], current['phase'], ' or '.join(allowed)), 'GOAL_INVALID_TRANSITION')
        if operation == 'resume':
            if current['phase'] == 'active' and cache['activation'] == 'armed':
                raise GoalError('goal "{}" is already active and armed'.format(current['id']), 'GOAL_INVALID_TRANSITION')
            if cache['state']['roundsStarted'] >= current['maxGoalRounds']:
                raise GoalError('goal "{}" exhausted {} goal rounds; increase maxGoalRounds before resuming'.format(
                    current['id'], current['maxGoalRounds']), 'GOAL_INVALID_TRANSITION')
        goal = dict(current, revision=current['revision'] + 1, phase=phase)
        goal.pop('blockedReason', None)
        if operation == 'block':
            code, message = (reason.get('code'), reason.get('message')) if isinstance(reason, dict) else (None, None)
            if (not isinstance(code, str) or re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', code) is None
                    or not isinstance(message, str) or not trim_js(message)):
                raise GoalError('goal block reason requires a lower-kebab-case code and a non-empty message', 'GOAL_INVALID_BLOCK_REASON')
            goal['blockedReason'] = dict(code=code, message=trim_js(message))
        return self._snapshot(agent, cache, operation, goal, activation)

    def block(self, agent, ref, reason):
        return self._transition(agent, ref, 'block', ('active',), 'blocked', 'disarmed', reason)


class CurrentGoalRoundDriver(GoalRoundDriver):
    def queued(self, agent):
        return agent.inbox.nextTurn

    def pending(self, agent):
        return agent.inbox.nextStep + agent.inbox.nextTurn

    def cancelled(self, payload):
        return payload['signal'].aborted

    def wait_idle(self, agent):
        return agent.whenIdle()

    def dropped_attempt_matches(self, attempt, goal):
        return attempt['goalId'] == goal['id'] and attempt['revision'] == goal['revision']

    def changed(self, payload):
        agent = payload['agent']
        if (payload['change']['operation'] == 'pause' and agent.status == 'running'
                and self.ctx.get('agents').current_initiator() is not agent):
            agent.cancel({'kind': 'user'}, {'keepInbox': True})
        super().changed(payload)


class CurrentToolGoal(CanonicalToolGoal):
    inject = ['agents', 'goals', 'tools', 'systemPrompt', 'sessionProjections']

    def apply(self, ctx):
        threshold = self.config.get('blockedAfterConsecutiveRounds')
        try:
            integer(3 if threshold is None else threshold, 1)
        except (ValueError, TypeError, OverflowError):
            raise TypeError('blockedAfterConsecutiveRounds must be a positive safe integer')
        self.config = dict(self.config, blockedAfterConsecutiveRounds=3 if threshold is None else threshold)
        super().apply(ctx)

    def execution(self, execution):
        agent = getattr(execution, 'agent', None)
        if agent is None:
            raise HarnessError('goal tools require a calling agent', 'GOAL_TOOL_AGENT_REQUIRED')
        agents = self.ctx.get('agents')
        if agents.get(agent.id) is not agent or agent.status != 'running' or agents.current_initiator() is not agent:
            raise HarnessError('goal tools require the exact live calling agent inside its active driver', 'GOAL_TOOL_DRIVER_REQUIRED')
        events = agent.session.snapshotEvents()
        boundary = self.ctx.get('sessionProjections').stateOf(agent.session, 'turnBoundary')
        if boundary is None or boundary['openTurnStartSeq'] is None:
            raise HarnessError('goal tools require an open model turn', 'GOAL_TOOL_DRIVER_REQUIRED')
        return agent, events[boundary['openTurnStartSeq'] + 1:]

    def human(self, agent, events):
        return agent in self.ctx.get('agents').roots() and any(
            event['type']=='user/message' and event['data']['source']['kind']=='user' for event in events)

    def require_human(self, agent, events):
        if not self.human(agent, events):
            raise HarnessError('this goal operation requires a direct human turn on a top-level agent', 'GOAL_TOOL_AUTHORITY_REQUIRED')

    def authority(self, agent, events):
        if self.human(agent, events):
            return None
        goal = self.ctx.get('goals').get(agent)
        if goal:
            for event in events:
                source = event['data'].get('source', {}) if event['type']=='user/message' else {}
                if (source.get('kind')=='goal' and source.get('goalId')==goal['id'] and
                        source.get('revision')==goal['revision'] and source.get('round')==goal['roundsStarted']):
                    return goal
        raise HarnessError('complete and blocked require a direct human turn or the current goal round', 'GOAL_TOOL_AUTHORITY_REQUIRED')

    async def get(self, args, execution):
        agent, _ = self.execution(execution)
        return goal_value(self.ctx.get('goals').get(agent))

    async def create(self, args, execution):
        agent, events = self.execution(execution)
        self.require_human(agent, events)
        request = dict(objective=args['objective'])
        if 'max_goal_rounds' in args:
            request['maxGoalRounds'] = args['max_goal_rounds']
        return goal_value(self.ctx.get('goals').create(agent, request))

    async def update(self, args, execution):
        agent, events = self.execution(execution)
        def invalid(message):
            raise HarnessError(message, 'GOAL_TOOL_INVALID_UPDATE')
        key, revision, action = args['goal_id'], args['revision'], args['action']
        try:
            if not key or trim_js(key) != key:
                raise ValueError()
            integer(revision, 1)
        except (ValueError, TypeError, OverflowError):
            invalid('goal_id must be non-empty and revision must be a positive safe integer')
        ref, goals = dict(id=key, revision=revision), self.ctx.get('goals')
        replacements = {}
        if 'objective' in args and args['objective'] != '':
            replacements['objective'] = args['objective']
        if 'max_goal_rounds' in args and args['max_goal_rounds'] != 0:
            replacements['maxGoalRounds'] = args['max_goal_rounds']
        reason = args.get('blocked_reason', '')
        if action == 'edit':
            self.require_human(agent, events)
            if reason != '':
                invalid('blocked_reason is valid only with action blocked')
            return goal_value(goals.edit(agent, ref, replacements))
        if action in ('pause', 'resume'):
            self.require_human(agent, events)
            if replacements or reason != '':
                invalid('objective and max_goal_rounds are valid only with action edit; blocked_reason is valid only with action blocked')
            self.assert_resume(goals, agent, ref, action)
            return goal_value(getattr(goals, action)(agent, ref))
        authority = self.authority(agent, events)
        if replacements:
            invalid('objective and max_goal_rounds are valid only with action edit')
        if action == 'complete' and reason != '':
            invalid('blocked_reason is valid only with action blocked')
        if action == 'blocked' and ('blocked_reason' not in args or not trim_js(reason)):
            invalid('blocked_reason is required with action blocked')
        if action == 'blocked' and authority and authority['roundsStarted'] < self.threshold:
            raise HarnessError('blocked requires at least {} consecutive goal rounds; current round is {}'.format(
                self.threshold, authority['roundsStarted']), 'GOAL_TOOL_BLOCK_THRESHOLD')
        goal = goals.complete(agent, ref) if action == 'complete' else goals.block(agent, ref, dict(code='model-reported', message=reason))
        if authority:
            execution.deferContext(create_user_message(dict(content=render_wrapup(goal['objective'], reason if action=='blocked' else None),
                source=dict(kind='plugin', plugin='tool-goal', form='notice', summary=summary(action + ': ' + goal['objective'])))))
        return goal_value(goal)

    def assert_resume(self, goals, agent, ref, action):
        current = goals.get(agent)
        if action == 'resume' and current and goal_ref(current) == ref and current['phase'] == 'paused':
            raise HarnessError('the model cannot resume a paused goal; the user must resume it', 'GOAL_TOOL_RESUME_PAUSED')
