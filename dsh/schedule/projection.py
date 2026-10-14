"""Strict active schedule projection with an immutable inherited event cut."""
from dsh.core.session.types import SessionLogOffset
from dsh.schedule.domain import decode_schedule_change, apply_schedule_changes
from dsh.schedule.types import FoldedSchedules


def schedule_state(value):
    if not isinstance(value, dict) or set(value) != {'inheritedEventCount', 'active', 'seenIds'}:
        raise ValueError('invalid schedule projection state')
    cut = SessionLogOffset(value['inheritedEventCount'])
    if not isinstance(value['active'], list) or not isinstance(value['seenIds'], list):
        raise ValueError('invalid schedule projection arrays')
    seen = [decode_schedule_change(dict(version=1, operation='delete', id=item))['id']
            for item in value['seenIds']]
    active = [decode_schedule_change(dict(version=1, operation='create', schedule=record))['schedule'].to_dict()
              for record in value['active']]
    ids = [record['id'] for record in active]
    if len(set(seen)) != len(seen) or len(set(ids)) != len(ids) or any(item not in seen for item in ids):
        raise ValueError('invalid schedule projection identities')
    return dict(inheritedEventCount=cut, active=active, seenIds=seen)


def apply_schedule(state, event):
    if event['seq'] < state['inheritedEventCount'] or event['type'] != 'schedule/change':
        return state
    records = [decode_schedule_change(dict(version=1, operation='create', schedule=record))['schedule']
               for record in state['active']]
    folded = apply_schedule_changes(FoldedSchedules(records, state['seenIds']),
                                    [decode_schedule_change(event['data'])])
    return dict(inheritedEventCount=state['inheritedEventCount'],
                active=[record.to_dict() for record in folded.active], seenIds=folded.seenIds)


def schedule_records(value):
    if not isinstance(value, list):
        raise ValueError('schedule records must be an array')
    return [decode_schedule_change(dict(version=1, operation='create', schedule=record))['schedule'].to_dict()
            for record in value]


SCHEDULE_DEFINITION = dict(key='schedule', stateVersion=2, stateSchema=schedule_state,
    init=lambda _header, cut: dict(inheritedEventCount=cut, active=[], seenIds=[]), apply=apply_schedule,
    wire=dict(view=lambda state: state['active'], viewSchema=schedule_records))
