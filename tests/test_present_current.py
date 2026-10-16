"""Explicit delivery commit, Agent ownership and actual durable file references."""
import json
from pathlib import Path

import pytest

from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.tools import ToolExecutionInput
from dsh.fs.fs_local import FsLocalPlugin
from dsh.fs.tool_present_current import CurrentToolPresent
from scripts.oracles.present_current_python import execute
from scripts.session_format_oracle import json_equal
from tests.test_agent_machine_current import mount

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/present_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_delivery_contract(case):
    assert json_equal(execute(case),case['expected'])


@pytest.mark.parametrize('value',[0,-1,1.5,float('inf'),float('nan'),True,None,9007199254740992,10**400])
def test_invalid_deployment_limit_registers_nothing(value):
    ctx=Context()
    with pytest.raises(ValueError,match='positive integer maxFiles'):
        CurrentToolPresent(config=dict(maxFiles=value)).apply(ctx)
    assert ctx.get('tools') is None


@pytest.mark.asyncio
async def test_actual_binary_delivery_survives_cold_read_without_copying_or_inheritance(tmp_path):
    parent_dir,child_dir=tmp_path/'parent',tmp_path/'child'
    parent_dir.mkdir();child_dir.mkdir()
    path=parent_dir/'报告.docx';path.write_bytes(b'PK\x00\xff')
    ctx=await mount(tmp_path)
    await ctx.plugin(FsLocalPlugin,dict(cwd=str(child_dir)))
    fiber=await ctx.plugin(CurrentToolPresent)
    parent=await ctx.get('agents').create(dict(sessionId='parent',options=dict(provider='script',model='model'),meta=dict(cwd=str(parent_dir))))
    child=await ctx.get('agents').create(dict(sessionId='child',parentAgent=parent.agent,options=dict(provider='script',model='model'),meta=dict(cwd=str(child_dir),parentSession='parent',origin='subagent',delegationDepth=1)))
    try:
        parent.agent.session.append('turn/start',dict(turn=1))
        child.agent.session.append('turn/start',dict(turn=1))
        # FS reads must never participate in declaring a file, including binary outputs.
        async def forbidden(*args,**kwargs):raise AssertionError('present read or copied file contents')
        ctx.get('fs').readBytes=forbidden
        ctx.get('fs').readText=forbidden
        signal=AbortController().signal
        result=await ctx.get('tools').execute(ToolExecutionInput('parent-call','present',dict(files=[dict(path='报告.docx',description='Report')]),agent=parent.agent,signal=signal))
        assert not result.isError and result.value['turn']==1
        assert ctx.get('attachments') is None
        assert not any(e['type']=='deliverables/presented' for e in child.agent.session.snapshotEvents())
        outside=await ctx.get('tools').execute(ToolExecutionInput('child-call','present',dict(files=[dict(path='../parent/报告.docx')]),agent=child.agent,signal=signal))
        assert not outside.isError
        path.write_bytes(b'updated source')
        assert path.read_bytes()==b'updated source'
        await child.dispose();await parent.dispose()
        for sid,call,declared in [('parent','parent-call','报告.docx'),('child','child-call','../parent/报告.docx')]:
            read=await ctx.get('sessionPersistence').open(sid,'read')
            try:
                events=(await read.read())['events']
                deliveries=[e['data'] for e in events if e['type']=='deliverables/presented']
                assert len(deliveries)==1 and deliveries[0]['callId']==call
                assert deliveries[0]['files'][0]['path']==declared
            finally:await read.close()
        await fiber.dispose()
        assert ctx.get('tools').get('present') is None
    finally:await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_post_block_retires_pending_and_next_success_commits_once(tmp_path):
    (tmp_path/'output').write_bytes(b'output')
    ctx=await mount(tmp_path);await ctx.plugin(FsLocalPlugin,dict(cwd=str(tmp_path)))
    await ctx.plugin(CurrentToolPresent)
    handle=await ctx.get('agents').create(dict(sessionId='one',options=dict(provider='script',model='model'),meta=dict(cwd=str(tmp_path))))
    owner=handle.agent;owner.session.append('turn/start',dict(turn=1))
    blocked=[True]
    async def policy(execution,result,next_fn):
        outcome=await next_fn()
        return dict(kind='block',feedback=[dict(type='text',text='blocked')]) if blocked[0] else outcome
    ctx.on('tools/post-execute',policy)
    try:
        for index in range(2):
            result=await ctx.get('tools').execute(ToolExecutionInput('call-'+str(index),'present',dict(files=[dict(path='output')]),agent=owner,signal=AbortController().signal))
            assert result.isError is (index==0)
            blocked[0]=False
        deliveries=[e['data'] for e in owner.session.snapshotEvents() if e['type']=='deliverables/presented']
        assert len(deliveries)==1 and deliveries[0]['callId']=='call-1'
    finally:await ctx.fiber.dispose()
