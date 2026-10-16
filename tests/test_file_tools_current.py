"""Current scoped file tools and their real filesystem consumers."""
import json
from pathlib import Path

import pytest

from dsh.core.abort import AbortController
from dsh.core.tools import ToolExecutionInput
from dsh.fs.fs_local import FsError, FsLocalPlugin
from dsh.fs.fs_observation_policy import FsObservationPolicyPlugin
from dsh.fs.tool_fs_mutation import remediate_fs_error
from dsh.fs.tools_current import CurrentToolFs
from scripts.oracles.file_tools_current_python import execute
from scripts.session_format_oracle import json_equal
from tests.test_agent_machine_current import mount

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/file_tools_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_file_tools_contract(case):
    assert json_equal(execute(case),case['expected'])


@pytest.mark.parametrize('error',[ValueError('plain'),FsError('permission','FS_PERMISSION_DENIED'),FsError('original read','FS_NOT_OBSERVED'),FsError('version changed','FS_STALE_VERSION')])
def test_remediation_preserves_original_cause_and_other_error_identity(error):
    mapped=remediate_fs_error(error,'/workspace/output')
    if getattr(error,'code',None) in ('FS_NOT_OBSERVED','FS_STALE_VERSION'):
        assert mapped is not error and mapped.cause is error and mapped.code==error.code
        assert str(mapped)==('cannot modify "/workspace/output": file has not been read — read the file, then retry' if error.code=='FS_NOT_OBSERVED' else 'version changed — re-read the file, then retry')
    else:assert mapped is error


@pytest.mark.asyncio
async def test_real_agent_read_and_observation_guard_with_reversible_prompt_visibility(tmp_path):
    path=tmp_path/'existing.txt';path.write_bytes(b'original\n')
    ctx=await mount(tmp_path)
    await ctx.plugin(FsLocalPlugin,dict(cwd=str(tmp_path)))
    await ctx.plugin(FsObservationPolicyPlugin)
    fiber=await ctx.plugin(CurrentToolFs)
    handle=await ctx.get('agents').create(dict(sessionId='files',options=dict(provider='script',model='model'),meta=dict(cwd=str(tmp_path))))
    agent=handle.agent
    async def call(name,arguments):
        return await ctx.get('tools').execute(ToolExecutionInput('call-'+name,name,arguments,agent=agent,signal=AbortController().signal))
    try:
        denied=await call('edit',dict(file_path='existing.txt',old_string='original',new_string='updated'))
        assert denied.isError and 'file has not been read — read the file, then retry' in denied.content[0]['text']
        assert str(path) in denied.content[0]['text'] and path.read_bytes()==b'original\n'
        read=await call('read',dict(file_path='existing.txt'))
        assert not read.isError and read.value['lines'][0]['text']=='original'
        created=await call('write',dict(file_path='new.txt',content='created'))
        assert not created.isError and (tmp_path/'new.txt').read_bytes()==b'created'
        restriction=agent.ctx.get('tools').restrict(dict(allow=['read','write']))
        def sections(prompt):return {row['name']:row['text'] for row in prompt['sections'] if row['name'].startswith('tool:')}
        prompt=sections(await ctx.get('systemPrompt').assemble(dict(scope=agent)))
        assert prompt['tool:edit']=='' and 'prefer edit' not in prompt['tool:write'] and prompt['tool:read']
        restriction()
        assert 'prefer edit' in sections(await ctx.get('systemPrompt').assemble(dict(scope=agent)))['tool:write']
        await fiber.dispose()
        assert not sections(await ctx.get('systemPrompt').assemble(dict(scope=agent)))
        assert ctx.get('tools').get('read',agent) is None
    finally:await ctx.fiber.dispose()
