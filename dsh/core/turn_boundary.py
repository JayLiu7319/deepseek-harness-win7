"""Host turn/step boundary projection owned by the rc.1 Agent loop."""
from dsh.core.session.types import SessionSeq
from dsh.core.session.types import _is_safe_non_negative_int


def boundary_state(value):
    if not isinstance(value, dict):
        raise ValueError('invalid turn boundary projection')
    for key in ('openTurnStartSeq', 'lastStepStartSeq'):
        if value[key] is not None:
            SessionSeq(value[key])
    boundary = value['lastStepBoundary']
    if boundary is not None:
        if boundary['kind'] not in ('start', 'end'):
            raise ValueError('invalid step boundary kind')
        SessionSeq(boundary['seq'])
    if not _is_safe_non_negative_int(value['lastTurn']):
        raise ValueError('invalid turn boundary lastTurn')
    return dict(openTurnStartSeq=value['openTurnStartSeq'],
                lastStepStartSeq=value['lastStepStartSeq'],
                lastStepBoundary=None if boundary is None else dict(kind=boundary['kind'], seq=boundary['seq']),
                lastTurn=value['lastTurn'])


def apply_boundary(state, event):
    kind = event['type']
    if kind == 'turn/start':
        return dict(state, openTurnStartSeq=event['seq'], lastTurn=event['data']['turn'])
    if kind == 'turn/end':
        return dict(state, openTurnStartSeq=None)
    if kind == 'step/start':
        return dict(state, lastStepStartSeq=event['seq'], lastStepBoundary=dict(kind='start', seq=event['seq']))
    if kind == 'step/end':
        return dict(state, lastStepBoundary=dict(kind='end', seq=event['seq']))
    return state


TURN_BOUNDARY_DEFINITION = dict(
    key='turnBoundary', stateVersion=2, stateSchema=boundary_state,
    init=lambda header, cut: dict(openTurnStartSeq=None, lastStepStartSeq=None,
                                 lastStepBoundary=None, lastTurn=0),
    apply=apply_boundary,
)
