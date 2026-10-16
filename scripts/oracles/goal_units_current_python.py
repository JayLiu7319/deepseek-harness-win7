"""Strict replay, sticky failure and checkpoint admission through current units."""
from dsh.goal.fold_current import DEFINITION, apply_goal_event
from dsh.goal.fold import empty_goal_state


def run(test):
    if test['mode']=='checkpoint':
        try:return dict(accepted=True,value=DEFINITION['stateSchema'](test['input']))
        except (ValueError,TypeError,KeyError,OverflowError):return dict(accepted=False)
    state=DEFINITION['init']();folded=empty_goal_state();results=[]
    for event in test['events']:
        state=DEFINITION['apply'](state,event)
        try:
            apply_goal_event(folded,event)
            value={key:value for key,value in folded.items() if key!='seenGoalIds' and value is not None}
            results.append(dict(fold=value,state=state,view=DEFINITION['wire']['view'](state)))
        except ValueError as error:results.append(dict(error=str(error),state=state,view=DEFINITION['wire']['view'](state)))
    return results
