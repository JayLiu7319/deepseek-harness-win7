"""Pure request pricing and checkpoint admission against actual current units."""
from types import SimpleNamespace
from dsh.llm.token_meter_current import estimate_message,plan_surface,price_surface
from dsh.llm.token_projections_current import DEFINITIONS


def run(test):
    if test['mode']=='turn-usage':
        from dsh.llm.turn_usage_current import derive_turn_token_usage
        return dict(usage=derive_turn_token_usage(test['events']))
    if test['mode']=='estimate':return estimate_message(test['input'])
    if test['mode']=='checkpoint':
        definition=next(d for d in DEFINITIONS if d['key']==test['key'])
        try:return dict(accepted=True,value=definition['stateSchema'](test['input']))
        except (ValueError,TypeError,KeyError):return dict(accepted=False)
    nodes=[];trace=[]
    def prices(refs):trace.append(refs);return test.get('prices',[])
    try:
        for event in test.get('events',[]):
            node,target,delta=plan_surface(nodes,event)
            nodes[target[0]:target[1]]=[node]
        value=price_surface(nodes,SimpleNamespace(priceImages=prices) if 'prices' in test else None,
                            (lambda ref:'File '+ref['id']) if test.get('fileText') else None)
        return dict(nodes=nodes,value=value,trace=trace)
    except Exception as error:return dict(error=str(error),trace=trace,nodes=nodes)
