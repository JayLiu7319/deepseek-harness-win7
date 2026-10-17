import copy
import json

import pytest
import yaml

from dsh.boot.profile_boot import admit_historical_persona_patches, run_profile


def test_admission_is_scoped_recursive_and_does_not_mutate_user_rows():
    rows = [dict(insert=[dict(id='group', name='group', config=[
        dict(id='persona', config=dict(text='old', prefix='', suffix='tail')),
        dict(id='system-prompt', name='custom-plugin', config=dict(persona='custom')),
        dict(name='@deepseek-ai/dsh-system-prompt', config=dict(persona='legacy'))])])]
    before = copy.deepcopy(rows)
    actual = admit_historical_persona_patches(rows)[0]['insert'][0]['config']
    assert rows == before
    assert actual[0]['config'] == dict(prefix='', suffix='tail')
    assert actual[1]['config'] == dict(persona='custom')
    assert actual[2]['config'] == dict(personaPrefix='legacy')


@pytest.mark.asyncio
async def test_saved_profile_persona_reaches_current_prompt_without_rewriting(tmp_path, monkeypatch):
    plugin, old_key, text = 'system-prompt', 'persona', 'Saved deployment persona'
    home = tmp_path / 'home'
    directory = home / 'profiles/custom'
    directory.mkdir(parents=True)
    (directory / 'package.json').write_text(json.dumps(dict(name='upgrade-test', private=True,
        dsh=dict(profile=dict(bundles=[], patchReload='startup')))), encoding='utf-8')
    rows = [dict(insert=[dict(id='system-prompt', name='@deepseek-ai/dsh-system-prompt')])]
    rows.append(dict(id=plugin, config={old_key: text}))
    patch = directory / 'cordis.patch.yml'
    patch.write_text(yaml.safe_dump(rows), encoding='utf-8')
    original = patch.read_bytes()
    monkeypatch.setenv('DSH_HOME', str(home))
    result = await run_profile(dict(profile='custom', dshHome=str(home), waitForExit=False))
    try:
        prompt = result['ctx'].get('systemPrompt')
        assert prompt.layers.global_layer.sections.data['deployment:persona-prefix']['text'] == text
        assert patch.read_bytes() == original
    finally:
        result['shutdown'].shutdown(0)
        await result['shutdown'].wait()


@pytest.mark.asyncio
async def test_retired_agent_persona_key_reaches_scoped_current_provider():
    from dsh.core.persona_current import CurrentPersonaPlugin
    from dsh.core.agent_dispatch_current import assemble_context_for
    from dsh.core.system_prompt import render_prompt
    from tests.test_agent_machine_current import mount, create
    ctx = await mount()
    handle = await create(ctx, 'upgrade-persona')
    try:
        row = admit_historical_persona_patches([dict(name=CurrentPersonaPlugin.name,
            config=dict(text='Saved agent persona', suffix='saved tail'))])[0]
        await handle.agent.ctx.plugin(CurrentPersonaPlugin, row['config'])
        prompt = await ctx.get('systemPrompt').assemble(assemble_context_for(handle.agent))
        assert render_prompt(prompt).endswith('Saved agent persona\n\nsaved tail')
    finally:
        await handle.dispose()
        await ctx.fiber.dispose()
