"""Actual Source desktop intents and real shell-free Python child ownership."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

from dsh.core.abort import AbortController
from dsh.host.native_command_current import run_native_command
from scripts.oracles.native_path_current_python import execute
from scripts.session_format_oracle import json_equal

CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/native_path_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_source_native_desktop_boundary(case):
    assert json_equal(execute(case), case['expected'])


@pytest.mark.asyncio
async def test_actual_child_utf8_literal_argv_and_failed_exit():
    signal = AbortController().signal
    arguments = ['literal & | > <', "a'b\"c", '目录, file', '$(echo unsafe)']
    result = await run_native_command(sys.executable, ['-X', 'utf8', '-c', 'import json,sys; print(json.dumps(sys.argv[1:],ensure_ascii=False)); print("诊断",file=sys.stderr)'] + arguments, signal)
    assert json.loads(result['stdout']) == arguments
    assert result['stderr'].strip() == '诊断'
    with pytest.raises(RuntimeError) as raised:
        await run_native_command(sys.executable, ['-X', 'utf8', '-c', 'import sys; print("output"); print("failure",file=sys.stderr); sys.exit(7)'], signal)
    assert (raised.value.code, raised.value.stdout.strip(), raised.value.stderr.strip()) == (7, 'output', 'failure')
    assert not signal._listeners


@pytest.mark.asyncio
async def test_child_abort_terminates_and_reaps_process(tmp_path):
    marker, controller = tmp_path / 'started', AbortController()
    task = asyncio.create_task(run_native_command(sys.executable, ['-c', 'import pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(str(__import__("os").getpid()),encoding="utf-8"); time.sleep(60)', str(marker)], controller.signal))
    for _ in range(200):
        if marker.exists():
            break
        await asyncio.sleep(.01)
    assert marker.exists()
    reason = RuntimeError('caller disconnected'); controller.abort(reason)
    with pytest.raises(RuntimeError) as raised:
        await asyncio.wait_for(task, 3)
    assert raised.value is reason
    assert not controller.signal._listeners


@pytest.mark.asyncio
async def test_preaborted_runner_does_not_spawn(tmp_path):
    marker, controller = tmp_path / 'forbidden', AbortController()
    controller.abort()
    with pytest.raises(RuntimeError):
        await run_native_command(sys.executable, ['-c', 'import pathlib,sys; pathlib.Path(sys.argv[1]).touch()', str(marker)], controller.signal)
    assert not marker.exists()
