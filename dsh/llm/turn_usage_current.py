"""Exact completed-turn accounting requires every embedded attempt boundary."""
import math
from dsh.core.session.json import UNDEFINED
from dsh.llm.assistant_stream import lastAssistantStreamChunk


def count(value):
    return type(value) in (int,float) and math.isfinite(value) and value==int(value) and 0<=value<=9007199254740991


def safe_sum(values):
    total=0
    for value in values:
        total+=value
        if not count(total):return None
    return total


def stream_usage(stream):
    chunk=lastAssistantStreamChunk(stream,'usage')
    return None if chunk is UNDEFINED else chunk['usage']


def normalize(usage,route=None):
    if usage is None:return None
    if any(not count(usage.get(key)) for key in ('inputTokens','outputTokens')):return None
    if any(key in usage and not count(usage[key]) for key in ('cacheReadTokens','cacheWriteTokens','reasoningTokens')):return None
    if usage.get('reasoningTokens',0)>usage['outputTokens']:return None
    prompt=safe_sum([usage['inputTokens'],usage.get('cacheReadTokens',0),usage.get('cacheWriteTokens',0)])
    if prompt is None:return None
    if 'totalTokens' in usage:
        total=usage['totalTokens']
        if not count(total):return None
        exact=total-usage['outputTokens']
        if not count(exact) or exact<prompt:return None
        if all(key in usage for key in ('cacheReadTokens','cacheWriteTokens')) and exact!=prompt:return None
    else:
        if not all(key in usage for key in ('cacheReadTokens','cacheWriteTokens')):return None
        total=safe_sum([prompt,usage['outputTokens']])
        if total is None:return None
    return dict(inputTokens=usage['inputTokens'],outputTokens=usage['outputTokens'],totalTokens=total,
        **{key:usage[key] for key in ('cacheReadTokens','cacheWriteTokens','reasoningTokens') if key in usage},
        **(dict(route=route) if route is not None else {}))


def aggregate(attempts):
    if not attempts:return None
    values={key:safe_sum([row[key] for row in attempts]) for key in ('inputTokens','outputTokens','totalTokens')}
    if any(value is None for value in values.values()):return None
    result=dict(uncachedInputTokens=values['inputTokens'],outputTokens=values['outputTokens'],totalTokens=values['totalTokens'])
    for key in ('cacheReadTokens','cacheWriteTokens','reasoningTokens'):
        if all(key in row for row in attempts):result[key]=safe_sum([row[key] for row in attempts])
    if all('route' in row for row in attempts):
        routes={}
        for row in attempts:routes[(row['route']['provider'],row['route']['model'])]=row['route']
        result['routes']=list(routes.values())
    return result


def derive_turn_token_usage(events):
    state=dict(kind='idle');attempts=[];turn=None;saw_end=False;invalid=False
    def close(route=None):
        if state['kind']!='open':return False
        value=normalize(state.get('sample'),route)
        if value is None:return False
        attempts.append(value);return True
    def same(data):return state.get('turn')==data['turn'] and state.get('step')==data['step']
    for event in events:
        if invalid:break
        kind,data=event['type'],event['data']
        if kind=='turn/start':
            if turn is not None or state['kind']!='idle':invalid=True
            else:turn=data['turn']
            continue
        if turn is None:invalid=True;break
        if kind=='turn/end':
            if data['turn']!=turn or state['kind']!='idle' or saw_end:invalid=True
            else:saw_end=True
            continue
        if saw_end:invalid=True;break
        if kind=='step/start':
            if data['turn']!=turn or state['kind']!='idle':invalid=True
            else:state=dict(kind='open',turn=turn,step=data['step'])
        elif kind=='llm/retry-started':
            if data['turn']!=turn or state['kind']!='settled' or state['by']!='retry' or not same(data):invalid=True
            else:state=dict(kind='open',turn=turn,step=data['step'])
        elif kind in ('assistant/attempt','assistant/message'):
            if data['turn']!=turn or state['kind']!='open' or not same(data):invalid=True;continue
            sample=data.get('usage') if kind=='assistant/message' else None
            if sample is None:sample=stream_usage(data['stream'])
            if sample is not None:state=dict(state,sample=sample)
            route=None
            if kind=='assistant/message':
                source=data['message']['source']
                if source['provider'] and source['model']:route=dict(provider=source['provider'],model=source['model'])
            if not close(route):invalid=True
            else:state=dict(kind='finishClosed',turn=turn,step=data['step']) if kind=='assistant/attempt' else dict(kind='settled',turn=turn,step=data['step'],by='message')
        elif kind=='llm/retry':
            if data['turn']!=turn or state['kind']=='idle' or not same(data):invalid=True;continue
            if state['kind']=='settled' or state['kind']=='open' and not close():invalid=True
            if not invalid:state=dict(kind='settled',turn=turn,step=data['step'],by='retry')
        elif kind=='step/end':
            if data['turn']!=turn or state['kind']=='idle' or not same(data):invalid=True;continue
            if state['kind']=='open' and not close():invalid=True
            if not invalid:state=dict(kind='idle')
    return None if invalid or not saw_end or state['kind']!='idle' else aggregate(attempts)


deriveTurnTokenUsage=derive_turn_token_usage
