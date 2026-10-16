"""v3 positional pressure: in-history system messages and embedded attempts."""
import copy

from dsh.cordis.json_text import stringify_json
from dsh.cordis.utils import _js_string_length
from dsh.core.session.current import SURFACE_EVENT_TYPES
from dsh.core.session.current_surface import deriveEventMessage
from dsh.core.session.current_request_header import canonicalHeader, headerEquals
from dsh.core.session.json import deep_freeze
from dsh.llm.assistant_stream import assembleAssistantStream
from dsh.llm.token_meter import TokenMeter, TokenMeterPlugin, usage_tokens
from dsh.llm.token_estimate import (estimate_message as old_estimate_message, estimate_content,
    estimate_tools_tokens, estimate_structural_block, ROLE_OVERHEAD, CHARS_PER_TOKEN)


def isSurfaceEvent(event):
    return event['type'] in SURFACE_EVENT_TYPES and 'surfaceOp' in event


def estimate_message(message):
    if message['role'] != 'system':
        return old_estimate_message(message)
    if not message['content']:
        return 0
    chars = sum(_js_string_length(block['text'] if block['type']=='text' else stringify_json(block)) for block in message['content'])
    return (chars+CHARS_PER_TOKEN-1)//CHARS_PER_TOKEN+ROLE_OVERHEAD


def analyze(event):
    message=deriveEventMessage(event)
    node=dict(seq=event['seq'],heuristicTokens=0 if message is None else estimate_message(message),
              imageStructuralTokens=0,fileStructuralTokens=0,images=[],files=[])
    def collect(blocks):
        for block in blocks:
            kind=block['type']
            if kind in ('image','file'):
                node['images' if kind=='image' else 'files'].append(block['attachment'])
                node[kind+'StructuralTokens']+=estimate_structural_block(block)
            elif kind=='tool-result':collect(block['content'])
    if message is not None:collect(message['content'])
    return node


def plan_surface(nodes,event):
    node=analyze(event);tokens=node['heuristicTokens'];op=event['surfaceOp']
    if op=='append':return node,(len(nodes),len(nodes)),tokens
    positions={item['seq']:index for index,item in enumerate(nodes)}
    first,last=positions.get(op['startSeq']),positions.get(op['endSeq'])
    if first is None or last is None or first>last:
        raise ValueError('token surface: replace at seq %s has invalid current range %s-%s' % (event['seq'],op['startSeq'],op['endSeq']))
    return node,(first,last+1),tokens-sum(item['heuristicTokens'] for item in nodes[first:last+1])


def price_surface(nodes,pricing=None,file_text=None):
    refs=[ref for node in nodes for ref in node['images']] if pricing is not None else []
    has_files=file_text is not None and any(node['files'] for node in nodes)
    prices=pricing.priceImages(refs) if pricing is not None and (refs or has_files) else []
    if len(prices)!=len(refs):
        raise ValueError('token meter: route image pricing answered %s prices for %s occurrences' % (len(prices),len(refs)))
    cursor=0;result=[]
    for node in nodes:
        tokens=node['heuristicTokens']
        if file_text is not None and node['files']:
            tokens-=node['fileStructuralTokens']
            tokens+=sum(estimate_content([dict(type='text',text=file_text(ref))]) for ref in node['files'])
        if pricing is not None and node['images']:
            tokens-=node['imageStructuralTokens']
            for ref in node['images']:
                price=prices[cursor];cursor+=1
                tokens+=price['visualTokens']+estimate_content([dict(type='text',text=price['text'])])
        result.append(dict(seq=node['seq'],tokens=tokens,heuristicTokens=node['heuristicTokens']))
    return dict(nodes=result,surfaceTokens=sum(node['tokens'] for node in result))


class CurrentTokenMeter(TokenMeter):
    def __init__(self,ctx=None,config=None):
        from dsh.llm.token_projections_current import DEFINITIONS
        self.projection_definitions=DEFINITIONS
        super().__init__(ctx,config)

    def _fold(self,session,state,event):
        kind,data,seq=event['type'],event['data'],event['seq']
        header,step,anchor=state['header'],state['stepStart'],state['anchor']
        if kind=='request/header':header=canonicalHeader(data['header'])
        elif kind=='step/start':
            if step is not None:
                raise ValueError('token meter: step/start at seq %s arrived before turn %s/step %s ended' % (seq,step['turn'],step['step']))
            step=dict(data)
        elif kind=='step/end':
            if step is None or (step['turn'],step['step'])!=(data['turn'],data['step']):
                raise ValueError('token meter: step/end at seq %s has no matching step/start event' % seq)
            step=None
        node=target=None
        if isSurfaceEvent(event):node,target,delta=plan_surface(state['surface'],event)
        if kind=='assistant/message':
            opening=state['stepStart']
            if opening is None or (opening['turn'],opening['step'])!=(data['turn'],data['step']):
                raise ValueError('token meter: assistant/message at seq %s has no matching step/start event' % seq)
            usage=data.get('usage') if header is not None else None
            tokens=node['heuristicTokens']
            if usage is not None:
                blocks=assembleAssistantStream(data['stream']).blocks()
                tokens=estimate_content(blocks)+ROLE_OVERHEAD if blocks else 0
            anchor=dict(header=header,nodes=list(state['surface']),assistantTokens=tokens,usage=usage)
        state['header'],state['stepStart'],state['anchor']=header,step,anchor
        if node is not None:state['surface'][target[0]:target[1]]=[node]

    def measure(self,session,request_header=None):
        state=self._sync(session);header=state['header'] if request_header is None else canonicalHeader(request_header)
        llm=self.ctx.get('llm') if self.ctx is not None else None
        pricing=file_text=None
        if llm is not None:
            file_text=getattr(llm,'fileRequestText',None)
            if header is not None:
                resolve=getattr(llm,'imageRequestPricing',None)
                if resolve is not None:pricing=resolve(header['config']['provider'],header['config']['model'])
        surface=price_surface(state['surface'],pricing,file_text);anchor=state['anchor']
        matches=anchor is not None and ((anchor['header'] is None and header is None)
            or anchor['header'] is not None and header is not None and headerEquals(anchor['header'],header))
        if matches:
            anchor_tokens=price_surface(anchor['nodes'],pricing,file_text)['surfaceTokens']+anchor['assistantTokens']
            estimated=estimate_tools_tokens(header)+anchor_tokens;usage=anchor['usage']
            baseline=dict(kind='usage',tokens=usage_tokens(usage),usage=usage) if usage is not None and usage_tokens(usage)>=estimated else dict(kind='estimated',tokens=estimated)
            delta=surface['surfaceTokens']-anchor_tokens
        elif header is None and surface['surfaceTokens']==0:baseline,delta=dict(kind='none',tokens=0),0
        else:baseline,delta=dict(kind='estimated',tokens=estimate_tools_tokens(header)+surface['surfaceTokens']),0
        return deep_freeze(copy.deepcopy(dict(logRevision=state['consumedEvents'],baseline=baseline,
            surfaceDeltaTokens=delta,totalTokens=max(0,baseline['tokens']+delta),**surface)))

    estimate_message=staticmethod(estimate_message)
    estimateMessage=staticmethod(estimate_message)


class CurrentTokenMeterPlugin(TokenMeterPlugin):
    inject=['sessionProjections']

    def apply(self,ctx):
        meter=CurrentTokenMeter(ctx,self.config)
        ctx.set_service('token_meter',meter)
