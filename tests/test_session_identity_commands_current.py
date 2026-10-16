"""Current create/model/title/fork contracts and actual durable Agent consumer."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.api.session_commands_current import CurrentSessionCommands
from dsh.session.canonical_title import SessionTitleService
from dsh.session.cold_read import readColdSessionLog
from dsh.typert.remote import RemoteError
from scripts.oracles.session_agents_current_python import execute
from scripts.oracles.generate_agent_loop_current_cases import message
from scripts.session_format_oracle import json_equal
from tests.test_session_agents_current import api_harness


CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_identity_commands_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_identity_commands(case):
    assert json_equal(execute(case), case['expected'])


@pytest.mark.asyncio
async def test_actual_command_fork_commits_completed_prefix_and_preserves_model_title(tmp_path):
    ctx, agents = await api_harness(tmp_path)
    await ctx.plugin(SessionTitleService, dict(fallbackMaxWords=5, fallbackMaxBytes=40, maxTitleBytes=80))
    ctx.set_service('workspaceRegistry', SimpleNamespace(list=lambda: [], get=lambda _: None))
    commands = CurrentSessionCommands(ctx, agents, str(tmp_path))
    requests = []
    ctx.on('llm/stream', lambda request, next: (requests.append(request), next())[1])
    try:
        assert await commands.create(dict(sessionId='parent')) == dict(sessionId='parent')
        selected = await commands.selectModel(dict(sessionId='parent', provider='script', model='chosen'))
        assert selected == dict(selected=dict(provider='script', model='chosen'))
        parent = ctx.get('agents').get('parent')
        parent.followup(message('completed work'))
        await asyncio.wait_for(parent.whenIdle(), 3)
        renamed = await commands.rename(dict(sessionId='parent', title='  Fork title\n '))
        assert renamed['title'] == 'Fork title'
        cut = parent.session.seq
        parent.session.append('turn/start', dict(turn=2))
        forked = await commands.fork(dict(sessionId='parent', atSeq=1))
        child = ctx.get('agents').get(forked['sessionId'])
        assert child is not None and child.session.header.isSeeded is True
        assert child.session.header.parentSession == 'parent' and child.session.header.origin is None
        assert child.session.inheritedEventCount == cut
        assert list(child.session.events[:cut]) == list(parent.session.events[:cut])
        assert child.session.events[cut]['type'] == 'session/end-seed'
        assert ctx.get('sessionTitle').get(child.session)['title'] == 'Fork title'
        assert agents.selectionFor(child).current.to_dict() == dict(provider='script', model='chosen')
        child.followup(message('fork continuation'))
        await asyncio.wait_for(child.whenIdle(), 3)
        assert requests[-1]['model'] == 'chosen'
        assert not ctx.get('agents').isOwnedBy(child.id, parent)
        with pytest.raises(RemoteError) as caught:
            await commands.fork(dict(sessionId='parent', atSeq=cut))
        assert caught.value.code == 'session/fork-unavailable'
        await child.session.flush()
        inspected = await readColdSessionLog(ctx.get('sessionPersistence'), child.id)
        assert inspected['header']['isSeeded'] and inspected['inheritedEventCount'] == cut
        assert inspected['events'][cut - 1]['type'] == 'session/title'
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_cold_attachment_observation_remote_failure_is_wrapped_as_source(tmp_path):
    ctx, agents = await api_harness(tmp_path)
    primary = RemoteError('session/agent-busy', 'upstream read refused', {})
    async def observe(*_):
        raise primary
    ctx.set_service('sessionQuery', SimpleNamespace(observeSession=observe))
    try:
        with pytest.raises(RemoteError) as caught:
            await CurrentSessionCommands(ctx, agents).attachment(dict(sessionId='cold', attachmentId='missing'))
        assert caught.value.code == 'gateway/internal'
        assert 'attachment authorization unavailable' in str(caught.value)
    finally:
        await ctx.fiber.dispose()
