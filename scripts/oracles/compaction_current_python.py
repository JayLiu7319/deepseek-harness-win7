"""Actual current compaction transactions with a deterministic priced meter."""
from dsh.compaction.current import CurrentCompactionEngine,select_compactable_range


async def run(ctx,session,test,normalize):
    calls=[]
    class Meter:
        def measure(self,subject):
            return dict(nodes=[dict(seq=seq,tokens=10000,heuristicTokens=10000) for seq in subject.surface.nodes])
        def estimate_message(self,message):return 1
    meter=Meter();ctx.set_service('tokenMeter',meter)
    engine=CurrentCompactionEngine(ctx=ctx,config=dict(auto=False))
    async def summarize(input,agent,signal=None):
        calls.append(input)
        return dict(summary=[dict(type='text',text='summary')],provider='test',model='model')
    engine.summarize=summarize;results=[]
    for retain in test.get('retain',[0]):
        results.append(select_compactable_range(session,meter.measure(session),retain))
    if test.get('compact') and results[0] is not None:
        selected=results[0]
        result=await engine.compact_region(session,selected['start'],selected['end'],manual=True)
    else:result=None
    return normalize(dict(ranges=results,calls=calls,result=result,events=session.snapshotEvents(),messages=session.deriveMessages(),nodes=session.surface.nodes))
