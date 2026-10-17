"""Whole-log stats fold and persisted-state/wire validation observations."""
from dsh.session.stats_current import STATS_DEFINITION as definition


def execute(test, decode):
    if test.get('operation') == 'schema':
        parser = definition['stateSchema'] if test['schema'] == 'state' else definition['wire']['viewSchema']
        try:
            return dict(accepted=True, value=parser(decode(test['value'])))
        except (ValueError, KeyError, TypeError):
            return dict(accepted=False)
    state = definition['init']()
    stages = []
    for event in decode(test['events']):
        updated = definition['apply'](state, event)
        stages.append(dict(same=updated is state, state=updated, view=definition['wire']['view'](updated)))
        state = updated
    return dict(version=definition['stateVersion'], stages=stages)
