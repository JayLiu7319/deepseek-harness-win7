"""Embedded-stream stats, real Agent persistence and projection cache boundaries."""
import json
from pathlib import Path

import pytest

from dsh.session.stats_current import CurrentSessionStatsPlugin, STATS_DEFINITION
from dsh.session.projections import SessionProjectionRegistry
from scripts.oracles.session_stats_current_python import execute
from scripts.oracles.session_format_python import decode
from tests.test_agent_machine_current import mount, create, message


CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/session_stats_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_frozen_source_stats(case):
    assert execute(case, decode) == case['expected']


@pytest.mark.asyncio
async def test_actual_agent_embedded_stream_stats_survive_disk_and_checkpoint(tmp_path):
    ctx = await mount(tmp_path)
    fiber = await ctx.plugin(CurrentSessionStatsPlugin)
    handle = await create(ctx, 'stats-durable')
    try:
        agent = handle.agent
        agent.followup(message('counted'))
        await agent.whenIdle()
        registry = ctx.get('sessionProjections')
        snapshot = registry.snapshot(agent.session, ['sessionStats'])
        figures = snapshot['values']['sessionStats']
        assert figures['turns'] == figures['steps'] == figures['ttftSteps'] == 1
        assert figures['llmMs'] >= figures['ttftMs'] >= 0
        assert not any(event['type'] == 'assistant/chunk' for event in agent.session.events)
        final = next(event for event in agent.session.events if event['type'] == 'assistant/message')
        assert final['data']['stream']
        checkpoint = registry.checkpoint(agent.session)
        expected = json.loads(json.dumps(snapshot))
        await handle.dispose()
        reader = await ctx.get('sessionPersistence').open('stats-durable', 'read')
        try:
            disk = await reader.read()
        finally:
            await reader.close()
        cold = SessionProjectionRegistry()
        cold.register(STATS_DEFINITION)
        replay = cold.restore({}, disk['events'], 0, reader.header)
        assert replay['snapshot'] == expected
        # A checkpoint taken with an open step must retain retry first-token
        # timing when only its final message is read on the next process.
        events = list(disk['events'])
        cut = next(i for i, event in enumerate(events) if event['type'] == 'assistant/message')
        prefix = cold.restore({}, events[:cut], 0, reader.header)
        tail = cold.restore(prefix['checkpoint'], events[cut:], cut, reader.header)
        assert tail['snapshot'] == expected
        restored = cold.restore(checkpoint, [], len(events), reader.header)
        assert restored['snapshot'] == expected
        await fiber.dispose()
        assert not registry.has('sessionStats')
        await ctx.plugin(CurrentSessionStatsPlugin)
        assert registry.snapshot(agent.session, ['sessionStats']) == expected
    finally:
        await handle.dispose()
        await ctx.fiber.dispose()
