"""Exclusive creation, no local-state inheritance and real launcher consumers."""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from dsh.boot.profile import PROFILE_TEMPLATES, init_profile, load_profile_directory
from dsh.boot.profile_boot import initialize_profile_from_default, prepare_profile, run_profile, INSTALL_ANCHOR
from dsh.boot.dump_config import run_dump_config
from scripts.oracles.profile_init_current_python import execute
from scripts.session_format_oracle import json_equal

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/profile_init_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_profile_init_contract(case):assert json_equal(execute(case),case['expected'])


def test_product_templates_remain_explicit_and_independent(tmp_path):
    for key,template in PROFILE_TEMPLATES.items():
        initialize_profile_from_default('custom-'+key,key,str(tmp_path))
        directory=tmp_path/'profiles'/('custom-'+key)
        manifest=json.loads((directory/'package.json').read_text(encoding='utf-8'))
        assert manifest['dependencies']=={} and manifest['dsh']['profile']==template
        assert 'fromDefaultProfile' not in manifest['dsh']['profile']
        with pytest.raises(RuntimeError,match='is shipped'):
            initialize_profile_from_default(key,'web',str(tmp_path))


def test_failure_removes_only_exclusively_claimed_directory_and_can_retry(tmp_path):
    other=tmp_path/'profiles'/'other';other.mkdir(parents=True);(other/'keep').write_text('keep',encoding='utf-8')
    def broken(directory,*args):
        Path(directory,'partial').write_text('partial',encoding='utf-8');raise RuntimeError('failed writing template')
    with patch('dsh.boot.profile_boot.init_profile',broken):
        with pytest.raises(RuntimeError,match='failed writing template'):
            initialize_profile_from_default('rescue','web',str(tmp_path))
    assert not (tmp_path/'profiles'/'rescue').exists() and (other/'keep').read_text(encoding='utf-8')=='keep'
    initialize_profile_from_default('rescue','web',str(tmp_path))
    assert (tmp_path/'profiles'/'rescue'/'package.json').is_file()


def test_cleanup_failure_preserves_both_causes_and_partial_files(tmp_path):
    first,second=RuntimeError('write failed'),OSError('cleanup denied')
    with patch('dsh.boot.profile_boot.init_profile',side_effect=first),patch('dsh.boot.profile_boot.shutil.rmtree',side_effect=second):
        with pytest.raises(RuntimeError,match='could not be removed') as failure:
            initialize_profile_from_default('rescue','web',str(tmp_path))
    assert failure.value.errors==[first,second] and failure.value.__cause__ is first
    assert (tmp_path/'profiles'/'rescue').is_dir()


def test_two_synchronized_actual_processes_only_one_can_claim_profile(tmp_path):
    child=tmp_path/'claim.py'
    child.write_text('''import sys,time
from pathlib import Path
from dsh.boot.profile_boot import initialize_profile_from_default
home=Path(sys.argv[1]);(home/sys.argv[2]).write_text('ready',encoding='utf-8')
deadline=time.monotonic()+10
while not (home/'start').exists():
 if time.monotonic()>deadline:raise RuntimeError('barrier timeout')
 time.sleep(.01)
try:initialize_profile_from_default('rescue',sys.argv[3],str(home))
except RuntimeError as error:
 print(str(error));raise SystemExit(1)
''',encoding='utf-8')
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]));children=[]
    try:
        for index,template in enumerate(('web','headless')):
            children.append(subprocess.Popen([sys.executable,str(child),str(tmp_path),'ready'+str(index),template],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE))
        deadline=time.monotonic()+8
        while not all((tmp_path/('ready'+str(i))).exists() for i in range(2)):
            assert time.monotonic()<deadline;time.sleep(.01)
        (tmp_path/'start').write_text('start',encoding='utf-8')
        results=[process.communicate(timeout=8) for process in children]
        assert sorted(process.returncode for process in children)==[0,1],results
        manifest=json.loads((tmp_path/'profiles'/'rescue'/'package.json').read_text(encoding='utf-8'))
        winner=next(i for i,process in enumerate(children) if process.returncode==0)
        assert manifest['dsh']['profile']==PROFILE_TEMPLATES[('web','headless')[winner]]
    finally:
        for process in children:
            if process.poll() is None:process.kill()
            process.communicate(timeout=5)


def test_dump_initializes_once_and_preserves_patch_bytes_on_rejection(tmp_path):
    text=run_dump_config('rescue',True,dsh_home=str(tmp_path),from_default_profile='web')
    assert '@deepseek-ai/dsh-web-app' in text or 'web-app' in text
    directory=tmp_path/'profiles'/'rescue';user=directory/'cordis.patch.yml'
    user.write_text('- id: hand-edited\n  disabled: true\n',encoding='utf-8');before=user.read_bytes()
    with pytest.raises(RuntimeError,match='already exists'):
        run_dump_config('rescue',True,dsh_home=str(tmp_path),from_default_profile='web')
    assert user.read_bytes()==before


def test_application_owned_profile_loads_without_home_or_shipped_normalization(tmp_path):
    directory=tmp_path/'application'/'desktop';init_profile(str(directory),[], 'startup')
    (directory/'cordis.patch.yml').write_text('broken: [yaml',encoding='utf-8')
    loaded=load_profile_directory('test',str(directory),INSTALL_ANCHOR,dict(userLayer=False))
    assert loaded.name=='desktop' and loaded.patchReload=='startup' and loaded.patches==[] and loaded.layers==[]
    with pytest.raises(Exception):load_profile_directory('test',str(directory),INSTALL_ANCHOR)


@pytest.mark.asyncio
async def test_profile_run_initializes_before_python_lease_claim_then_boots_actual_tree(tmp_path):
    # The public run_profile claims an installer/host lease before its internal
    # compose. Initialization must happen first, or the lease's mkdir falsely
    # makes a fresh target look like pre-existing state.
    from dsh.cordis.environment import LaunchEnvironmentSnapshot
    with patch.dict(PROFILE_TEMPLATES,{'fixture':dict(bundles=[],patchReload='startup')}):
        result=await asyncio.wait_for(run_profile(dict(profile='rescue',fromDefaultProfile='fixture',dshHome=str(tmp_path),environment=LaunchEnvironmentSnapshot([]),args=[],waitForExit=False)),10)
    try:
        assert result['ctx'].get('loader') is not None
        assert (tmp_path/'profiles'/'rescue'/'package.json').is_file()
    finally:
        await result['ctx'].fiber.dispose()
