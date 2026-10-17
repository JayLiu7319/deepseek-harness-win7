"""Real filesystem resolution, literal argv and detached process ownership."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from dsh.host.open_in_app_resolver_current import launch_detached_app, resolve_internals, output, launch_resolved
from scripts.oracles.open_in_app_current_python import execute
from scripts.session_format_oracle import json_equal

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/open_in_app_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_open_in_app_contract(case):
    assert json_equal(execute(case),case['expected'])


def test_resolution_requires_composition_subprocess_capability():
    with pytest.raises(RuntimeError,match='internals.resolveExecutable is required'):
        resolve_internals()


@pytest.mark.asyncio
async def test_probe_deadline_is_delivered_to_native_runner():
    observed=[]
    async def run(command,args,signal):
        await signal.wait_aborted();observed.append(signal.reason);signal.throwIfAborted()
    started=time.monotonic()
    assert await output('probe',['literal'],25,dict(run=run)) is None
    assert len(observed)==1 and isinstance(observed[0],TimeoutError)
    assert time.monotonic()-started<2


@pytest.mark.asyncio
async def test_real_detached_launcher_spawn_and_early_exit_failures(tmp_path):
    with pytest.raises(FileNotFoundError):
        await launch_detached_app(str(tmp_path/'missing.exe'),[],dict(watchMs=1000))
    with pytest.raises(RuntimeError,match='launcher exited with code 7, signal null'):
        await launch_detached_app(sys.executable,['-c','raise SystemExit(7)'],dict(watchMs=5000))
    await launch_detached_app(sys.executable,['-c','pass'],dict(watchMs=5000))


def test_real_detached_child_outlives_host_scrubs_credentials_and_preserves_literal_argv(tmp_path):
    # One short lived parent exits after the watch window. Its actual child
    # waits for this test's release file, then records that it survived it.
    child=tmp_path/'child.py';parent=tmp_path/'parent.py'
    child.write_text('''import json,os,sys,time
from pathlib import Path
root=Path(sys.argv[1])
keys=('DEEPSEEK_API_KEY','OPENAI_API_KEY','TEST_SECRET','DSH_PRIVATE','EXPLICIT_TOKEN','ELECTRON_RUN_AS_NODE','OPEN_APP_VISIBLE')
(root/'started.json').write_text(json.dumps(dict(argv=sys.argv[2:],env={key:os.environ.get(key) for key in keys},pid=os.getpid())),encoding='utf-8')
deadline=time.monotonic()+15
while not (root/'release').exists() and time.monotonic()<deadline:time.sleep(.01)
(root/'finished').write_text('survived',encoding='utf-8')
''',encoding='utf-8')
    parent.write_text('''import asyncio,sys
from dsh.host.open_in_app_resolver_current import launch_detached_app
asyncio.run(launch_detached_app(sys.executable,sys.argv[1:],dict(watchMs=40,env=dict(EXPLICIT_TOKEN='adapter-value',ELECTRON_RUN_AS_NODE='1'),windowsHide=True)))
''',encoding='utf-8')
    env=dict(os.environ,DEEPSEEK_API_KEY='private',OPENAI_API_KEY='private',TEST_SECRET='private',DSH_PRIVATE='private',OPEN_APP_VISIBLE='inherited')
    env['PYTHONPATH']=str(Path(__file__).resolve().parents[1])
    literal=["a b';&$(literal)",'--cd=C:\\one two\\', '{path}']
    try:
        completed=subprocess.run([sys.executable,str(parent),str(child),str(tmp_path)]+literal,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        assert completed.returncode==0,completed.stderr.decode('utf-8','replace')
        deadline=time.monotonic()+5
        while not (tmp_path/'started.json').exists() and time.monotonic()<deadline:time.sleep(.01)
        observed=json.loads((tmp_path/'started.json').read_text(encoding='utf-8'))
        assert observed['argv']==literal
        assert observed['env']==dict(DEEPSEEK_API_KEY=None,OPENAI_API_KEY=None,TEST_SECRET=None,DSH_PRIVATE=None,EXPLICIT_TOKEN='adapter-value',ELECTRON_RUN_AS_NODE='1',OPEN_APP_VISIBLE='inherited')
        assert not (tmp_path/'finished').exists()
    finally:
        (tmp_path/'release').write_text('release owned child',encoding='utf-8')
        deadline=time.monotonic()+5
        while not (tmp_path/'finished').exists() and time.monotonic()<deadline:time.sleep(.01)
    assert (tmp_path/'finished').read_text(encoding='utf-8')=='survived'


@pytest.mark.asyncio
async def test_shell_open_watch_does_not_abort_late_opener_or_surface_late_failure():
    entered=asyncio.Event();release=asyncio.Event();signals=[]
    async def run(command,args,signal):
        assert command=='powershell.exe';assert args[-1]=="Invoke-Item -LiteralPath 'C:/work''s directory'"
        entered.set();signals.append(signal);await release.wait();raise RuntimeError('late failure')
    async def resolver(_):return None
    result=await launch_resolved(dict(launch=dict(kind='shell-open')),"C:/work's directory",25,dict(platform='win32',run=run,resolveExecutable=resolver))
    assert result=='launched' and entered.is_set() and not signals[0].aborted
    release.set();await asyncio.sleep(0);await asyncio.sleep(0)
    assert not signals[0].aborted
