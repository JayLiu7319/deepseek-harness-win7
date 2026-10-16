"""Current system head survives a real auxiliary LLM call and v3 commit."""
import json
from pathlib import Path

import pytest

from dsh.compaction.current import CurrentCompactionEngine
from scripts.oracles.agent_loop_current_python import execute
from scripts.oracles.session_format_python import decode
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.agent_machine_current_python import ScriptAdapter
from scripts.oracles.generate_agent_loop_current_cases import message
from tests.test_agent_machine_current import mount


CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/compaction_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_compaction_transaction(case):assert execute(case,decode)==case['expected']


@pytest.mark.asyncio
async def test_manual_summary_replays_system_once_and_commits_v3_range(tmp_path):
    ctx=await mount(tmp_path);requests=[]
    handle=await ctx.get('agents').create(dict(sessionId='compact',agentOptions=dict(provider='script',model='model')))
    session=handle.agent.session
    class Meter:
        def measure(self,subject):return dict(nodes=[dict(seq=seq,tokens=10000,heuristicTokens=10000) for seq in subject.surface.nodes])
        def estimate_message(self,value):return 1
    ctx.set_service('tokenMeter',Meter())
    ctx.on('llm/stream',lambda request,next:(requests.append(request),next())[1])
    try:
        head=session.append('system/message',dict(turn=1,step=1,message=dict(id='system',role='system',source=dict(kind='plugin',plugin='@deepseek-ai/dsh-system-prompt'),content=[dict(type='text',text='protected system')])),surface_op='append')
        first=session.append('user/message',message('earlier facts'),surface_op='append')
        tail=session.append('user/message',message('recent question'),surface_op='append')
        tools=[dict(name='test',description='test',parameters=dict(type='object',properties={}))]
        session.append('request/header',dict(header=dict(config=dict(provider='script',model='model'),tools=tools)))
        result=await CurrentCompactionEngine(config=dict(auto=False),ctx=ctx).compact_now(handle.agent)
        assert result['shadowedSeqs']==[first['seq']]
        assert head['seq'] in session.surface.nodes and tail['seq'] in session.surface.nodes
        assert first['seq'] not in session.surface.nodes
        assert requests[0]['messages'][0]['role']=='system'
        assert sum(message['role']=='system' for message in requests[0]['messages'])==1
        assert 'system' not in requests[0] and requests[0]['tools']==tools
        replacement=next(e for e in session.events if isinstance(e.get('surfaceOp'),dict))
        assert replacement['surfaceOp']==dict(op='replace',startSeq=first['seq'],endSeq=first['seq'])
    finally:await handle.dispose();await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_pruner_uses_current_surface_coordinates():
    from dsh.compaction.current import CurrentToolResultPruner
    from dsh.core.session.current_session import CurrentSession
    from dsh.cordis.context import Context
    from types import SimpleNamespace
    ctx=Context();ctx.set_service('tokenMeter',SimpleNamespace(estimate_message=lambda value:100))
    session=CurrentSession.create('prune')
    original=session.append('tool/result',dict(turn=1,step=1,message=dict(id='tool-result',role='user',source=dict(kind='tool',callId='call'),
        content=[dict(type='tool-result',toolCallId='call',content=[dict(type='text',text='x'*500)])])),surface_op='append')
    try:
        result=CurrentToolResultPruner(ctx=ctx,config=dict(thresholdChars=128,headChars=16,tailChars=8)).prune_session(session)
        assert result['pruned'][0]['originalSeq']==original['seq']
        replacement=session.eventAt(session.surface.nodes[0])
        assert replacement['surfaceOp']==dict(op='replace',startSeq=original['seq'],endSeq=original['seq'])
        assert len(replacement['data']['message']['content'][0]['content'][0]['text'])<128
    finally:await ctx.fiber.dispose()
