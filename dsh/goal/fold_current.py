"""rc.3 strict durable goal replay and checkpoint-safe host projection."""
import copy
import math
import re

from dsh.cordis.text import trim_js
from dsh.goal.fold import empty_goal_state, integer


def number(value, field, minimum=0):
    try:
        return integer(value, minimum)
    except (ValueError, TypeError, OverflowError):
        qualifier = 'positive' if minimum else 'non-negative'
        raise ValueError('goal change {} must be a {} safe integer'.format(field, qualifier))


def normalized(value):
    return isinstance(value, str) and bool(trim_js(value)) and trim_js(value) == value


def decode_snapshot(value):
    if not isinstance(value, dict):
        raise ValueError('goal change goal must be a record')
    if not isinstance(value.get('id'), str) or not value['id']:
        raise ValueError('goal change goal.id must be a non-empty string')
    if not normalized(value.get('objective')):
        raise ValueError('goal change goal.objective must be non-empty and normalized')
    phase = value.get('phase')
    if phase not in ('active', 'paused', 'blocked', 'complete'):
        raise ValueError('goal change goal.phase is invalid')
    keys = 'id,maxGoalRounds,objective,phase,revision'
    if phase == 'blocked':
        keys = 'blockedReason,' + keys
    if ','.join(sorted(value)) != keys:
        raise ValueError('goal change goal for phase {} must have exactly {} fields'.format(phase, keys))
    number(value['revision'], 'goal.revision', 1)
    number(value['maxGoalRounds'], 'goal.maxGoalRounds', 1)
    if phase == 'blocked':
        reason = value['blockedReason']
        if not isinstance(reason, dict) or set(reason) != {'code', 'message'}:
            raise ValueError('goal change goal.blockedReason must have exactly code and message fields')
        if not isinstance(reason['code'], str) or re.fullmatch(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*', reason['code']) is None:
            raise ValueError('goal change goal.blockedReason.code must be lower-kebab-case')
        if not normalized(reason['message']):
            raise ValueError('goal change goal.blockedReason.message must be non-empty and normalized')
    return copy.deepcopy(value)


def decode_goal_change(value):
    if not isinstance(value, dict) or value.get('kind') != 'goal/change':
        return None
    if type(value.get('version')) not in (int, float) or value['version'] != 1:
        version = value.get('version', 'undefined')
        if version is None:
            version = 'null'
        elif type(version) is bool:
            version = str(version).lower()
        raise ValueError('unsupported goal change version {}'.format(version))
    if value.get('operation') == 'clear':
        keys = 'cleared,clearedAt,kind,operation,version'
        if ','.join(sorted(value)) != keys:
            raise ValueError('goal clear change must have exactly {} fields'.format(keys))
        ref = value['cleared']
        if not isinstance(ref, dict) or set(ref) != {'id', 'revision'}:
            raise ValueError('goal clear tombstone must have exactly id and revision fields')
        if not isinstance(ref['id'], str) or not ref['id']:
            raise ValueError('goal clear tombstone id must be a non-empty string')
        number(ref['revision'], 'cleared.revision', 1)
        number(value['clearedAt'], 'clearedAt')
    else:
        if value.get('operation') not in ('create', 'edit', 'pause', 'resume', 'complete', 'block'):
            raise ValueError('goal change operation is invalid')
        keys = 'createdAt,goal,kind,operation,roundsStarted,updatedAt,version'
        if ','.join(sorted(value)) != keys:
            raise ValueError('goal snapshot change must have exactly {} fields'.format(keys))
        number(value['createdAt'], 'createdAt')
        number(value['updatedAt'], 'updatedAt')
        if value['updatedAt'] < value['createdAt']:
            raise ValueError('goal change updatedAt cannot precede createdAt')
        decode_snapshot(value['goal'])
        number(value['roundsStarted'], 'roundsStarted')
    return copy.deepcopy(value)


def apply_goal_event(state, event):
    if event['type'] == 'user/message':
        source = event['data']['source']
        if source.get('kind') != 'goal':
            return
        try:
            if not isinstance(source.get('goalId'), str) or not source['goalId']:
                raise ValueError()
            integer(source.get('revision'), 1)
            integer(source.get('round'), 1)
        except (ValueError, TypeError, OverflowError):
            raise ValueError('goal message source is invalid')
        current = state['goal']
        if (current is None or current['phase'] != 'active' or source['goalId'] != current['id']
                or source['revision'] != current['revision'] or source['round'] != state['roundsStarted'] + 1
                or source['round'] > current['maxGoalRounds']):
            raise ValueError('goal round at session event {} is not the next admitted round of the active goal'.format(event['seq']))
        state['roundsStarted'] = source['round']
        return
    if event['type'] != 'goal/change':
        return
    change = decode_goal_change(event['data'])
    if change is None:
        raise ValueError('goal change at session event {} has an invalid kind'.format(event['seq']))
    operation, current = change['operation'], state['goal']
    goal = change.get('goal', change.get('cleared'))
    if operation == 'create':
        if (goal['revision'] != 1 or goal['phase'] != 'active' or change['roundsStarted'] != 0
                or current is not None and current['phase'] != 'complete' or goal['id'] in state['seenGoalIds']):
            raise ValueError('goal create requires a fresh active revision-one goal with zero rounds')
    else:
        if current is None:
            raise ValueError('goal {} requires a current goal'.format(operation))
        if goal['id'] != current['id'] or goal['revision'] != current['revision'] + 1:
            raise ValueError('goal {} must advance the current goal by one revision'.format(operation))
        if operation == 'clear':
            if change['clearedAt'] < state['updatedAt']:
                raise ValueError('goal clear timestamp cannot precede the current goal update')
        else:
            if (change['createdAt'] != state['createdAt'] or change['updatedAt'] < state['updatedAt']
                    or change['roundsStarted'] != state['roundsStarted']):
                raise ValueError('goal {} does not preserve the current counters and timestamps'.format(operation))
            if operation == 'edit':
                if goal['phase'] != current['phase'] or goal.get('blockedReason') != current.get('blockedReason'):
                    raise ValueError('goal edit cannot change phase or blocked reason')
            else:
                if any(goal[key] != current[key] for key in ('objective', 'maxGoalRounds')):
                    raise ValueError('goal {} cannot change objective or maxGoalRounds'.format(operation))
                allowed, target = {'pause': (('active',), 'paused'), 'resume': (('active', 'paused', 'blocked'), 'active'),
                                   'complete': (('active', 'paused', 'blocked'), 'complete'), 'block': (('active',), 'blocked')}[operation]
                invalid = current['phase'] not in allowed or goal['phase'] != target
                if operation == 'resume':
                    invalid = invalid or state['roundsStarted'] >= goal['maxGoalRounds']
                if invalid:
                    suffix = ' or exhausted round budget' if operation == 'resume' else ''
                    raise ValueError('goal {} has an invalid phase transition{}'.format(operation, suffix))
    state['lastRef'] = {'id': goal['id'], 'revision': goal['revision']}
    if operation == 'clear':
        state.update(goal=None, roundsStarted=0, createdAt=None, updatedAt=None)
    else:
        if operation == 'create':
            state['seenGoalIds'].add(goal['id'])
        state.update({key: copy.deepcopy(change[key]) for key in ('goal', 'roundsStarted', 'createdAt', 'updatedAt')})


def init_projection(*_):
    return {'current': None, 'seenGoalIds': [], 'failure': None}


def apply_projection(state, event):
    if state['failure'] is not None or (event['type'] != 'goal/change' and
            (event['type'] != 'user/message' or event['data']['source'].get('kind') != 'goal')):
        return state
    folded = empty_goal_state()
    if state['current'] is not None:
        folded.update(copy.deepcopy(state['current']))
    folded['seenGoalIds'] = set(state['seenGoalIds'])
    try:
        apply_goal_event(folded, event)
    except ValueError as error:
        return dict(state, failure='goal replay failed at session event {}: {}'.format(event['seq'], error))
    seen = list(state['seenGoalIds'])
    if folded['goal'] is not None and folded['goal']['id'] not in seen:
        seen.append(folded['goal']['id'])
    current = None if folded['goal'] is None else {key: folded[key] for key in ('goal', 'roundsStarted', 'createdAt', 'updatedAt')}
    return dict(current=current, seenGoalIds=seen, failure=None)


def view_schema(value):
    if value is None:
        return None
    if not isinstance(value, dict) or not isinstance(value.get('goal'), dict):
        raise ValueError('invalid goal projection')
    goal = value['goal']
    for key in ('id', 'objective'):
        if not isinstance(goal.get(key), str) or not goal[key]:
            raise ValueError('invalid goal text')
    if goal.get('phase') not in ('active', 'paused', 'blocked', 'complete'):
        raise ValueError('invalid goal phase')
    for key in ('revision', 'maxGoalRounds'):
        integer(goal.get(key), 1)
    integer(value.get('roundsStarted'))
    for key in ('createdAt', 'updatedAt'):
        if type(value.get(key)) not in (int, float) or not math.isfinite(value[key]):
            raise ValueError('invalid goal timestamp')
    result = {key: copy.deepcopy(value[key]) for key in ('roundsStarted', 'createdAt', 'updatedAt')}
    result['goal'] = {key: goal[key] for key in ('id', 'revision', 'objective', 'phase', 'maxGoalRounds')}
    if 'blockedReason' in goal:
        reason = goal['blockedReason']
        if not isinstance(reason, dict) or any(not isinstance(reason.get(key), str) for key in ('code', 'message')):
            raise ValueError('invalid goal blocked reason')
        result['goal']['blockedReason'] = {key: reason[key] for key in ('code', 'message')}
    return result


def state_schema(value):
    if not isinstance(value, dict) or set(value) != {'current', 'seenGoalIds', 'failure'}:
        raise ValueError('invalid goal state')
    seen, failure = value['seenGoalIds'], value['failure']
    if not isinstance(seen, list) or any(not isinstance(key, str) or not key for key in seen) or len(set(seen)) != len(seen):
        raise ValueError('invalid seen goal ids')
    if failure is not None and (not isinstance(failure, str) or not failure):
        raise ValueError('invalid goal failure')
    current = view_schema(value['current'])
    if current is not None and (current['goal']['id'] not in seen or current['updatedAt'] < current['createdAt']
                                or current['roundsStarted'] > current['goal']['maxGoalRounds']):
        raise ValueError('invalid goal state invariants')
    return dict(current=current, seenGoalIds=list(seen), failure=failure)


DEFINITION = dict(key='goal', stateVersion=6, stateSchema=state_schema, init=init_projection,
                  apply=apply_projection, wire=dict(viewSchema=view_schema, view=lambda state: state['current']))
