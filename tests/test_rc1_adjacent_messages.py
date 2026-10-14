import asyncio
from types import SimpleNamespace

import pytest

from dsh.core.abort import AbortController
from dsh.core.scope import scope_of
from dsh.subagent.errors import SubagentError
from dsh.subagent.runtime import SubagentPlugin
from dsh.subagent.in_process import SpawnInProcess
from dsh.subagent.control_tools import ToolSubagentControl
from dsh.session.persistence_jsonl_canonical import JsonlSessionPersistencePlugin
from test_subagent_in_process import setup
from test_subagent_continuation import BlockingModel, retired


async def composition(tmp_path, control=True):
    ctx, _, parent = await setup()
    model = BlockingModel()
    ctx.set_service('llm', model)
    await ctx.plugin(JsonlSessionPersistencePlugin, dict(root=str(tmp_path)))
    await ctx.plugin(SubagentPlugin)
    await ctx.plugin(SpawnInProcess)
    if control:
        await ctx.plugin(ToolSubagentControl)
    service = ctx.get('subagents')
    result = await service.startContinuable(dict(provider='spawn', childId='worker', label='worker',
        request=dict(parent=parent.agent, prompt=[dict(type='text', text='initial task')])) )
    await asyncio.wait_for(model.entered.wait(), 2)
    return ctx, model, parent, service, ctx.get('agents').get(result['childId'])


@pytest.mark.asyncio
async def test_adjacent_agent_steers_both_directions_and_host_queue_keeps_provenance(tmp_path):
    ctx, model, parent, service, child = await composition(tmp_path)
    signal = AbortController().signal
    try:
        tool = ctx.get('tools').get('send_message', scope_of(parent.agent.ctx))
        down = await tool.execute(dict(agent_id=child.id, message='change direction now'),
                                  SimpleNamespace(agent=parent.agent, signal=signal))
        up = await service.sendMessage(child, parent.agent.id, [dict(type='text', text='early finding')], dict(signal=signal))
        queue = await service.queuePrompt(parent.agent, child.id, [dict(type='text', text='human next turn')],
                                          dict(kind='user'), signal)
        assert len({down['messageId'], up, queue}) == 3
        model.release.set()
        await retired(service.continuations, child.id)
        await parent.agent.when_idle()
        persisted = await ctx.get('sessionPersistence').inspect(child.id)
        messages = {e['data']['id']: e['data'] for e in persisted.events if e['type'] == 'user/message'}
        assert messages[down['messageId']]['source'] == dict(kind='agent-message', form='relay', senderSessionId=parent.agent.id)
        assert messages[queue]['source'] == dict(kind='user')
        initial = next(iter(messages.values()))
        assert 'Your parent agent id is "parent"' in str(initial['content'])
        received = next(e['data'] for e in parent.agent.session.events if e['type'] == 'user/message' and e['data']['id'] == up)
        assert received['source'] == dict(kind='agent-message', form='relay', senderSessionId=child.id)
        assert received['content'][0]['text'] == 'Agent worker sent a message:'
    finally:
        model.release.set()
        await service.continuations.drain()
        await parent.dispose()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_absent_standard_adapter_omits_return_guidance(tmp_path):
    ctx, model, parent, service, child = await composition(tmp_path, control=False)
    try:
        assert 'Your parent agent id' not in str(model.requests)
    finally:
        model.release.set()
        await service.continuations.drain()
        await parent.dispose()
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_image_followup_refuses_before_inbox_acceptance_and_text_still_works(tmp_path):
    ctx, model, parent, service, child = await composition(tmp_path)
    calls = []
    async def resolve(provider, name, signal):
        calls.append((provider, name))
        return dict(inputModalities=['text'])
    model.resolve_model_info = resolve
    child.options.provider, child.options.model = 'fixture', 'text-only'
    try:
        with pytest.raises(SubagentError) as error:
            await service.sendMessage(parent.agent, child.id, [dict(type='image', attachment=dict(attachmentId='image'))],
                                      dict(signal=AbortController().signal))
        assert error.value.code == 'MODEL_DOES_NOT_SUPPORT_IMAGES'
        assert calls == [('fixture', 'text-only')]
        accepted = await service.sendMessage(parent.agent, child.id, [dict(type='text', text='valid text')],
                                              dict(signal=AbortController().signal))
        assert accepted and len(calls) == 1
    finally:
        model.release.set()
        await service.continuations.drain()
        await parent.dispose()
        await ctx.fiber.dispose()
