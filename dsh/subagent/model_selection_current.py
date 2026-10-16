"""Projection-owned, durable route authority for an explicit Session."""
import copy

from dsh.subagent.model_selection import validate_routes


KEY = 'subagentModelSelectionPolicy'


def routes(value):
    try:
        validate_routes(value)
    except ValueError as error:
        message = str(error)
        prefix = 'subagent model selection repeats route '
        if message.startswith(prefix):
            raise ValueError(prefix + '"' + message[len(prefix):] + '"')
        raise
    return value


def parse_state(value):
    if value is None:
        return None
    routes(value)
    if not value or any(set(route) != {'provider', 'model'} for route in value):
        raise ValueError('invalid subagent model selection checkpoint')
    return copy.deepcopy(value)


def apply(policy, event):
    if policy is not None or event['type'] != 'subagent/model-selection-policy':
        return policy
    allowed = routes(event['data']['allowedModels'])
    if not allowed:
        raise ValueError('subagent/model-selection-policy requires at least one route')
    return allowed


POLICY = dict(key=KEY, stateVersion=1, stateSchema=parse_state,
              init=lambda header, inherited_event_count: None, apply=apply)


def read_policy(projections, session):
    return copy.deepcopy(projections.stateOf(session, KEY))


def record_policy(projections, session, allowed):
    if read_policy(projections, session) is None:
        session.append('subagent/model-selection-policy', dict(allowedModels=copy.deepcopy(allowed)))
