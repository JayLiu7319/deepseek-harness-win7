"""Workspace instructions over current Agent requests and real filesystem reads."""
import asyncio
import copy
import json
from pathlib import Path

import pytest

from dsh.context.instructions_current import CurrentAgentInstructionsPlugin
from dsh.fs.fs_local import FsLocalPlugin
from dsh.fs.tools_current import CurrentToolFs
from scripts.oracles.agent_machine_current_python import ScriptAdapter
from scripts.oracles.generate_agent_machine_current_cases import response
from scripts.oracles.instructions_current_python import execute
from tests.test_agent_machine_current import mount, create, message

CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/instructions_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('value', [0, -1, 1.5, '10'])
def test_source_byte_cap_config_rejects_invalid_limits(value):
    assert CurrentAgentInstructionsPlugin.Config.validate(dict(maxBytes=65536, maxSourceBytes=value))['issues']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_current_original_instruction_journeys(case):
    assert execute(case) == case['expected']
    if case['case'] == 'instructions/same-version':
        assert len(case['expected'][-1]['reads']) == 1
    if case['case'] == 'instructions/touch-read':
        assert len(case['expected'][1]['decision']['messages']) == 2
        assert len(case['expected'][-1]['decision']['messages']) == 1


@pytest.mark.asyncio
async def test_actual_read_tool_updates_nested_instructions_only_after_the_committed_step(tmp_path):
    (tmp_path / '.git').mkdir()
    (tmp_path / 'AGENTS.md').write_text('root authority', encoding='utf-8')
    nested = tmp_path / 'sub'
    nested.mkdir()
    (nested / 'AGENTS.md').write_text('nested authority', encoding='utf-8')
    (nested / 'file.txt').write_text('read target', encoding='utf-8')
    ctx = await mount(tmp_path)
    await ctx.plugin(FsLocalPlugin, dict(cwd=str(tmp_path)))
    await ctx.plugin(CurrentToolFs)
    owner = await ctx.plugin(CurrentAgentInstructionsPlugin, dict(maxBytes=65536, dshHome=str(tmp_path / 'home')))
    requests, step_ends = [], []
    tool = dict(type='tool-call', id='read-one', name='read', arguments=json.dumps(dict(file_path=str(nested / 'file.txt'))))
    class Adapter(ScriptAdapter):
        async def stream(self, request):
            requests.append(copy.deepcopy(request['messages']))
            async for chunk in super().stream(request):
                yield chunk
    ctx.get('llm').registerAdapter(['instructions'], Adapter(dict(script=[[
        dict(type='block-start', index=0, blockType='tool-call'),
        dict(type='tool-call-delta', index=0, id=tool['id'], name=tool['name'], argumentsDelta=tool['arguments']),
        dict(type='block-end', index=0, block=tool), dict(type='finish', reason=dict(kind='tool-calls'))], response(), response(), response()])))
    def observe(session, event):
        if event['type'] == 'step/end':
            step_ends.append(event['seq'])
    ctx.on('session/event', observe)
    try:
        handle = await ctx.get('agents').create(dict(sessionId='instructions', agentOptions=dict(provider='instructions', model='model'), meta=dict(cwd=str(tmp_path))))
        agent = handle.agent
        agent.followup(message('first'))
        await asyncio.wait_for(agent.whenIdle(), 5)
        assert len(requests) == 2
        assert 'root authority' in str(requests[0]) and 'nested authority' not in str(requests[0])
        assert 'nested authority' in str(requests[1])
        contexts = [event for event in agent.session.events if event['type'] == 'user/message'
                    and event['data']['source']['kind'] == 'agent-instructions']
        assert len(contexts) == 2 and contexts[1]['seq'] > step_ends[0]
        assert contexts[0]['data']['source']['baseline'] is True
        (nested / 'AGENTS.md').write_text('updated nested authority', encoding='utf-8')
        agent.followup(message('second'))
        await asyncio.wait_for(agent.whenIdle(), 5)
        assert 'Updated instructions from:' in str(requests[-1])
        assert 'updated nested authority' in str(requests[-1])
        count = len([event for event in agent.session.events if event['type'] == 'user/message'
                     and event['data']['source']['kind'] == 'agent-instructions'])
        await owner.dispose()
        agent.followup(message('third'))
        await asyncio.wait_for(agent.whenIdle(), 5)
        assert len([event for event in agent.session.events if event['type'] == 'user/message'
                    and event['data']['source']['kind'] == 'agent-instructions']) == count
        await ctx.get('sessions').flush(agent.session)
        await handle.dispose()
        reader = await ctx.get('sessionPersistence').open('instructions', 'read')
        try:
            stored = (await reader.read())['events']
            assert any(event['type'] == 'user/message' and event['data']['source'].get('baseline') for event in stored)
        finally:
            await reader.close()
    finally:
        await ctx.fiber.dispose()
