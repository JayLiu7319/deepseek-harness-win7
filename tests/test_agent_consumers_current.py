"""Persona scope disposal, explicit child ownership and v3 output consumers."""
import asyncio
import json
from pathlib import Path

import pytest

from dsh.core.abort import AbortController
from dsh.core.persona_current import CurrentPersonaPlugin
from dsh.core.agent_dispatch_current import assemble_context_for
from dsh.core.system_prompt import render_prompt
from dsh.subagent.in_process_current import start_run
from dsh.subagent.assistant_output_current import AssistantOutputFold
from scripts.oracles.agent_machine_current_python import execute
from scripts.oracles.session_format_python import decode
from tests.test_agent_machine_current import mount, create


CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/agent_consumers_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_consumers(case):
    assert execute(case,decode)==case['expected']


@pytest.mark.asyncio
async def test_persona_scope_unload_restores_global_prefix_suffix_and_context():
    ctx=await mount();handle=await create(ctx,'persona')
    prompt=handle.agent.ctx.get('systemPrompt')
    ctx.get('systemPrompt').context(dict(name='runtime',order=1,text='dynamic'))
    try:
        before=await prompt.assemble(assemble_context_for(handle.agent))
        fiber=await handle.agent.ctx.plugin(CurrentPersonaPlugin,dict(prefix='scoped',suffix='tail',includeRuntimeContext=False))
        scoped=await prompt.assemble(assemble_context_for(handle.agent))
        assert render_prompt(scoped).endswith('scoped\n\ntail')
        assert not scoped['contexts']
        assert 'scoped' not in render_prompt(await ctx.get('systemPrompt').assemble({}))
        await fiber.dispose()
        restored=await prompt.assemble(assemble_context_for(handle.agent))
        assert restored==before
    finally:
        await handle.dispose();await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_child_setup_uses_explicit_subject_and_disposal_releases_scope():
    ctx=await mount();parent=await create(ctx,'parent');run=None
    try:
        request=dict(parent=parent.agent,signal=AbortController().signal,prompt=[dict(type='text',text='task')],
                     persona='child only',descriptor=dict(version=3,mode='one-shot',provider='test'))
        run=await start_run(request)
        assert ctx.get('agents').isOwnedBy(run.id,parent.agent)
        assert (await asyncio.wait_for(asyncio.shield(run.result),3))['stopReason']=='completed'
        assert 'child only' in render_prompt(await run.localAgent.ctx.get('systemPrompt').assemble(assemble_context_for(run.localAgent)))
        assert 'child only' not in render_prompt(await parent.agent.ctx.get('systemPrompt').assemble(assemble_context_for(parent.agent)))
        await run.dispose();await run.dispose()
        assert ctx.get('agents').get(run.id) is None
    finally:
        if run is not None:await run.dispose()
        await parent.dispose();await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_invalid_depth_precedes_abort_and_no_child_publication():
    ctx=await mount();parent=await create(ctx,'parent');control=AbortController();control.abort('stop')
    try:
        with pytest.raises(TypeError,match='maxDepth'):
            await start_run(dict(parent=parent.agent,signal=control.signal,maxDepth=-1))
        with pytest.raises(RuntimeError,match='before child publication'):
            await start_run(dict(parent=parent.agent,signal=control.signal))
        assert [agent.id for agent in ctx.get('agents').list()]==['parent']
    finally:
        await parent.dispose();await ctx.fiber.dispose()


def test_output_fold_reads_embedded_attempt_stream_and_borrows_last_nonempty_message():
    fold=AssistantOutputFold()
    fold.push(dict(type='assistant/chunk',data=dict(chunk=dict(type='text-delta',index=0,text='retired'))))
    assert fold.collect() is None
    stream=[dict(type='text-chunks',time0=1,index=0,dt=[1],texts=['partial',' text'])]
    fold.push(dict(type='assistant/attempt',data=dict(stream=stream)))
    assert fold.collect()==[dict(type='text',text='partial text')]
    content=[dict(type='text',text='final')]
    fold.push(dict(type='assistant/message',data=dict(message=dict(content=content),stream=[])))
    fold.push(dict(type='assistant/message',data=dict(message=dict(content=[]),stream=stream)))
    assert fold.collect() is content
