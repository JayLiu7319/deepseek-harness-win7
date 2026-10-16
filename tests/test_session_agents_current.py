"""Session activation policy plus real v3 durable activation and model routing."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.api.session_agents_current import CurrentSessionAgents, install_model_selection_projection, inspect_api_session
from dsh.core.model_selection import AgentDefaultModelConfig
from dsh.core.scope import scope_of
from dsh.session.query_current import CurrentSessionQueryService
from dsh.typert.registry import TypertRegistry
from scripts.oracles.session_agents_current_python import execute
from scripts.oracles.generate_agent_loop_current_cases import message
from scripts.session_format_oracle import json_equal
from tests.test_agent_machine_current import mount


CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_agents_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_activation_policy(case):
    assert json_equal(execute(case), case['expected'])


async def api_harness(tmp_path):
    ctx = await mount(tmp_path)
    await ctx.plugin(TypertRegistry)
    await ctx.plugin(AgentDefaultModelConfig, dict(provider='script', model='model'))
    ctx.set_service('sessionQuery', CurrentSessionQueryService(ctx))
    ctx.get('sessionProjections').register(dict(key='agentPreset', stateVersion=1, stateSchema=lambda value: value,
        init=lambda header, _: header.agentPreset, apply=lambda state, _: state))
    install_model_selection_projection(ctx)
    return ctx, CurrentSessionAgents(ctx)


@pytest.mark.asyncio
async def test_actual_create_deduplicates_identity_and_routes_pending_model(tmp_path):
    ctx, api = await api_harness(tmp_path)
    requests, mounted = [], []
    async def resolve(preset):
        return SimpleNamespace(id=preset or 'minimal')
    async def mount_preset(agent_ctx, preset):
        mounted.append((scope_of(agent_ctx), preset))
    ctx.set_service('agentPresets', SimpleNamespace(resolve=resolve, mount=mount_preset))
    ctx.on('llm/stream', lambda request, next: (requests.append(request), next())[1])
    try:
        agents = await asyncio.gather(*(api.ensureSession('actual', str(tmp_path/'project'), False) for _ in range(6)))
        agent = agents[0]
        assert all(item is agent for item in agents)
        assert mounted == [(agent, 'minimal')]
        assert agent.session.header.agentPreset == 'minimal'
        api.selectForNextRequest(agent, dict(provider='script', model='selected'))
        agent.followup(message('run'))
        await asyncio.wait_for(agent.whenIdle(), 3)
        assert len(requests) == 1 and requests[0]['model'] == 'selected'
        state = ctx.get('sessionProjections').stateOf(agent.session, 'modelSelection')
        assert state == dict(lastUsed=dict(provider='script', model='selected'), pending=None)
        assert (await api.resolveAgent('actual'))['agent'] is agent
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_actual_cold_restore_keeps_pending_selection_and_inspection_unpublished(tmp_path):
    ctx, api = await api_harness(tmp_path)
    requests = []
    ctx.on('llm/stream', lambda request, next: (requests.append(request), next())[1])
    try:
        composition = await api.composeAgent(None)
        handle = await ctx.get('agents').create(dict(sessionId='cold', agentOptions=api.agent_options(),
            meta=dict(cwd=str(tmp_path)), setup=composition['setup']))
        old = handle.agent
        api.selectForNextRequest(old, dict(provider='script', model='after-resume'))
        await handle.dispose()
        assert ctx.get('sessions').get('cold') is None
        inspected = await inspect_api_session(ctx, 'cold')
        assert inspected['meta'].id == 'cold' and ctx.get('sessions').get('cold') is None
        resolved = await asyncio.gather(*(api.resolveAgent('cold') for _ in range(5)))
        agent = resolved[0]['agent']
        assert agent is not old and all(item['agent'] is agent for item in resolved)
        assert api.selectionFor(agent).current.to_dict() == dict(provider='script', model='after-resume')
        agent.followup(message('resume'))
        await asyncio.wait_for(agent.whenIdle(), 3)
        assert requests[0]['model'] == 'after-resume'
        assert ctx.get('sessionProjections').stateOf(agent.session, 'modelSelection')['pending'] is None
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_waiter_cancellation_does_not_cancel_shared_creation(tmp_path):
    ctx, api = await api_harness(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    original = api._create_or_adopt
    async def delayed(*args):
        calls.append(args)
        entered.set()
        await release.wait()
        return await original(*args)
    api._create_or_adopt = delayed
    first = asyncio.ensure_future(api.ensureSession('shared', str(tmp_path), False))
    try:
        await entered.wait()
        second = asyncio.ensure_future(api.ensureSession('shared', str(tmp_path), False))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        agent = await asyncio.wait_for(second, 3)
        assert len(calls) == 1 and ctx.get('agents').get('shared') is agent
    finally:
        release.set()
        await ctx.fiber.dispose()
