"""Checkpoint-safe current usage, occupancy and retained-surface breakdown."""
import copy

from dsh.core.session.current_request_header import canonicalHeader
from dsh.core.session.json import UNDEFINED
from dsh.llm.assistant_stream import lastAssistantStreamChunk
from dsh.llm.token_meter_current import estimate_message, isSurfaceEvent, plan_surface
from dsh.core.session.current_surface import deriveEventMessage
from dsh.llm.token_estimate import estimate_tools_tokens
from dsh.llm.token_projections import (BUCKETS, _object, _counts as old_counts,
    _count as old_count, pressure_view)


def _count(value,positive=False):
    old_count(value,positive)
    if value>9007199254740991:raise ValueError('expected safe integral token count')


def _counts(value,required,optional=()):
    old_counts(value,required,optional)
    for key,number in value.items():_count(number,key=='contextWindow')
    return value


def usage_state(value):
    _object(value,('totals','last'));_counts(value['totals'],BUCKETS)
    result=dict(totals=copy.deepcopy(value['totals']),last=None)
    if value['last'] is not None:
        last=value['last'];_count(last['turn']);_count(last['step']);_counts(last['buckets'],BUCKETS)
        result['last']=dict(turn=last['turn'],step=last['step'],buckets=copy.deepcopy(last['buckets']))
    return result


def usage_of(event):
    if event['type']=='assistant/message' and 'usage' in event['data']:
        return event['data']['usage']
    if event['type'] not in ('assistant/message','assistant/attempt'):
        return None
    chunk=lastAssistantStreamChunk(event['data']['stream'],'usage')
    return None if chunk is UNDEFINED else chunk['usage']


def fold_usage(state,event):
    data,last=event['data'],state['last']
    if event['type']=='llm/retry-started':
        return dict(state,last=None) if last is not None and (last['turn'],last['step'])==(data['turn'],data['step']) else state
    usage=usage_of(event)
    if usage is None:return state
    buckets=dict(zip(BUCKETS,(usage['inputTokens'],usage['outputTokens'],usage.get('cacheReadTokens',0),usage.get('cacheWriteTokens',0))))
    previous=last['buckets'] if last is not None and (last['turn'],last['step'])==(data['turn'],data['step']) else None
    if previous==buckets:return state
    return dict(totals={key:state['totals'][key]-(previous or {}).get(key,0)+buckets[key] for key in BUCKETS},
                last=dict(turn=data['turn'],step=data['step'],buckets=buckets))


def fold_surface(claim,event):
    kind,data=event['type'],event['data']
    if kind in ('compaction/summary','compaction/prune'):
        return 0,dict(data['shadowedRange'],tokens=data['shadowedTokenCount'])
    if not isSurfaceEvent(event):return 0,None
    message=deriveEventMessage(event);tokens=0 if message is None else estimate_message(message)
    op=event['surfaceOp']
    if op=='append':return tokens,None
    if claim is None:return 0,None
    if (claim['start'],claim['end'])!=(op['startSeq'],op['endSeq']):
        raise ValueError('token surface: replace at seq %s over range %s-%s has no adjacent shadow price (armed claim covers %s-%s)' %
            (event['seq'],op['startSeq'],op['endSeq'],claim['start'],claim['end']))
    return tokens-claim['tokens'],None


def fold_pressure(state,event):
    delta,claim=fold_surface(state.get('claim'),event);result=state
    if event['type']=='request/context':
        window=event['data'].get('contextWindow')
        if window!=state.get('contextWindow'):
            result=dict(result);result.pop('contextWindow',None)
            if window is not None:result['contextWindow']=window
    usage=usage_of(event)
    if usage is not None:
        pressure=sum(usage.get(key,0) for key in ('inputTokens','cacheReadTokens','cacheWriteTokens'))
        if pressure!=result.get('pressureTokens') or result.get('sampledSurfaceTokens')!=result['surfaceTokens']:
            result=dict(result,pressureTokens=pressure,sampledSurfaceTokens=result['surfaceTokens'])
    if delta:result=dict(result,surfaceTokens=result['surfaceTokens']+delta)
    if state.get('claim') is None and claim is None:return result
    result=dict(result);result.pop('claim',None)
    if claim is not None:result['claim']=claim
    return result


def breakdown_state(value):
    _object(value,('nodes','breakdown'))
    if not isinstance(value['nodes'],list):raise ValueError('invalid token breakdown nodes')
    for node in value['nodes']:
        _object(node,('seq','heuristicTokens','system'));_count(node['seq']);_count(node['heuristicTokens'])
        if node['seq']>9007199254740991 or type(node['system']) is not bool:raise ValueError('invalid token breakdown node')
    _counts(value['breakdown'],('systemTokens','toolsTokens','messageTokens'))
    return copy.deepcopy(value)


def fold_breakdown(state,event):
    old=state['breakdown']
    if event['type']=='request/header':
        tools=estimate_tools_tokens(canonicalHeader(event['data']['header']))
        return state if tools==old['toolsTokens'] else dict(state,breakdown=dict(old,toolsTokens=tools))
    if not isSurfaceEvent(event):return state
    node,target,delta=plan_surface(state['nodes'],event)
    nodes=list(state['nodes']);nodes[target[0]:target[1]]=[dict(seq=event['seq'],heuristicTokens=node['heuristicTokens'],system=event['type']=='system/message')]
    system=next((node['heuristicTokens'] for node in reversed(nodes) if node['system'] and node['heuristicTokens']>0),0)
    messages=old['systemTokens']+old['messageTokens']+delta-system
    breakdown=old if system==old['systemTokens'] and messages==old['messageTokens'] else dict(systemTokens=system,toolsTokens=old['toolsTokens'],messageTokens=messages)
    return dict(nodes=nodes,breakdown=breakdown)


def parse_pressure(value):
    _object(value,('surfaceTokens',),('contextWindow','pressureTokens','sampledSurfaceTokens','claim'))
    result={key:number for key,number in value.items() if key!='claim'}
    _counts(result,('surfaceTokens',),('contextWindow','pressureTokens','sampledSurfaceTokens'))
    if 'claim' in value:
        claim={key:value['claim'][key] for key in ('start','end','tokens')}
        _counts(claim,('start','end','tokens'));result['claim']=claim
    return result


TOKEN_USAGE=dict(key='tokenUsage',stateVersion=2,stateSchema=usage_state,
    init=lambda _,cut:dict(totals=dict.fromkeys(BUCKETS,0),last=None),apply=fold_usage,
    wire=dict(viewSchema=lambda value:_counts(value,BUCKETS),view=lambda state:state['totals']))
CONTEXT_PRESSURE=dict(key='contextPressure',stateVersion=4,stateSchema=parse_pressure,
    init=lambda _,cut:dict(surfaceTokens=0),apply=fold_pressure,
    wire=dict(viewSchema=lambda value:_counts(value,(),('contextWindow','pressureTokens','projectedTokens')),view=pressure_view))
CONTEXT_BREAKDOWN=dict(key='contextBreakdown',stateVersion=4,stateSchema=breakdown_state,
    init=lambda _,cut:dict(nodes=[],breakdown=dict(systemTokens=0,toolsTokens=0,messageTokens=0)),apply=fold_breakdown,
    wire=dict(viewSchema=lambda value:_counts(value,('systemTokens','toolsTokens','messageTokens')),view=lambda state:state['breakdown']))
DEFINITIONS=(TOKEN_USAGE,CONTEXT_PRESSURE,CONTEXT_BREAKDOWN)
