import copy
import json
from pathlib import Path


def cases():
    rows=[]
    def add(mode,**extra):rows.append(dict(case=mode+'-'+str(len(rows)),kind='loop-current',operation='meter-units',mode=mode,**extra))
    for role in ('user','system','assistant'):
        for blocks in ([],[dict(type='text',text='')],[dict(type='text',text='abcdef')],[dict(type='text',text='x'),dict(type='text',text='y')],[dict(type='reasoning',text='hidden')],[dict(type='text',text='emoji \U0001f600')]):
            add('estimate',input=dict(role=role,content=blocks))
    for images in (False,True):
        for files in (False,True):
            blocks=[dict(type='text',text='hello')]
            if images:blocks.append(dict(type='image',attachment=dict(id='image')))
            if files:blocks.append(dict(type='file',attachment=dict(id='file')))
            for nested in (False,True):
                event=dict(seq=0,time=1000,type='user/message',surfaceOp='append',data=dict(role='user',content=blocks if not nested else [dict(type='tool-result',toolCallId='call',content=blocks)]))
                for pricing in (None,[],[dict(visualTokens=70,text='image prefix')]):
                    for text in (False,True):
                        add('price',events=[event],fileText=text,**(dict(prices=pricing) if pricing is not None else {}))
    states={
        'tokenUsage':dict(totals=dict(uncachedInputTokens=0,outputTokens=0,cacheReadTokens=0,cacheWriteTokens=0),last=None),
        'contextPressure':dict(surfaceTokens=0),
        'contextBreakdown':dict(nodes=[],breakdown=dict(systemTokens=0,toolsTokens=0,messageTokens=0))}
    for key,good in states.items():
        add('checkpoint',key=key,input=good)
        bad=dict(good,extra=1);add('checkpoint',key=key,input=bad)
        add('checkpoint',key=key,input={})
        for count in (True,-1,1.5,9007199254740992):
            bad=copy.deepcopy(good)
            (bad['totals'] if key=='tokenUsage' else bad['breakdown'] if key=='contextBreakdown' else bad)['outputTokens' if key=='tokenUsage' else 'systemTokens' if key=='contextBreakdown' else 'surfaceTokens']=count
            add('checkpoint',key=key,input=bad)
    event=dict(seq=0,time=1000,type='system/message',surfaceOp='append',data=dict(message=dict(role='system',content=[dict(type='text',text='system')])) )
    for start,end in ((0,0),(0,3),(3,0),(3,4)):
        changed=copy.deepcopy(event);changed['seq']=1;changed['surfaceOp']=dict(op='replace',startSeq=start,endSeq=end)
        add('price',events=[event,changed])
    add('checkpoint',key='tokenUsage',input=dict(states['tokenUsage'],last=dict(turn=1,step=1,buckets=states['tokenUsage']['totals'],extra='stripped')))
    add('checkpoint',key='contextPressure',input=dict(surfaceTokens=0,claim=dict(start=0,end=1,tokens=2,extra='stripped')))
    def event(kind,**extra):return dict(type=kind,data=dict(turn=1,step=1,**extra))
    good=dict(inputTokens=10,outputTokens=5,totalTokens=15)
    samples=[good,dict(inputTokens=10,outputTokens=5),dict(inputTokens=10,outputTokens=5,cacheReadTokens=0,cacheWriteTokens=0),
        dict(inputTokens=10,outputTokens=5,totalTokens=20),dict(inputTokens=10,outputTokens=5,totalTokens=14),
        dict(inputTokens=10,outputTokens=5,totalTokens=20,cacheReadTokens=0,cacheWriteTokens=0),
        dict(good,reasoningTokens=5),dict(good,reasoningTokens=6),dict(good,inputTokens=-1),dict(good,inputTokens=True),
        dict(good,totalTokens=9007199254740992),dict(good,inputTokens=1.5)]
    source=dict(kind='model',provider='provider',model='model')
    for sample in samples:
        for embedded in (False,True):
            data=dict(stream=[dict(type='chunk',time=1000,chunk=dict(type='usage',usage=sample))] if embedded else [],
                      message=dict(source=source))
            if not embedded:data['usage']=sample
            events=[event('turn/start'),event('step/start'),event('assistant/message',**data),event('step/end'),event('turn/end')]
            add('turn-usage',events=events)
    retry=[event('turn/start'),event('step/start'),event('assistant/attempt',stream=[dict(type='chunk',time=1000,chunk=dict(type='usage',usage=good))]),
        event('llm/retry'),event('llm/retry-started'),event('assistant/message',stream=[],usage=good,message=dict(source=source)),event('step/end'),event('turn/end')]
    for cut in range(len(retry)+1):add('turn-usage',events=retry[:cut])
    for index in (1,2,3,4,5,6):add('turn-usage',events=retry[:index]+retry[index+1:])
    return rows


if __name__=='__main__':
    Path(__file__).with_name('token_meter_units_current_cases.json').write_text(json.dumps(cases(),indent=2)+'\n',encoding='utf-8')
