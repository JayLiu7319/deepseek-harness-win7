"""Immutable historical bytes, validated staging and competing publication behavior."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.session.generation import (prepareJsonlMigration, verifyJsonlCurrentGeneration,
    createJsonlGenerationRuntime, JsonlGenerationSourceChangedError, JsonlGenerationTargetConflictError,
    NativeGenerationFileSystem, GenerationAggregateError, default_format_adapter)
from dsh.session.jsonl_current import generationLogFilename
from dsh.session.jsonl_zstd import compress_frame
from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/session_generation_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=[case['case'] for case in CASES])
def test_source_generation_filesystem_journey(case):
    assert json_equal(json.loads(json.dumps(observe(case))),dict(case['expected'],case=case['case']))


def source_bytes(version=2, seeded=False):
    header = dict(type='session',version=version,id='generation',createdAt=1,delegationDepth=0)
    if version >= 2:
        header['isSeeded'] = seeded
    elif seeded:
        header['seedLength'] = 0
    events = [dict(type='turn/start',seq=0,time=1,data=dict(turn=1)),
        dict(type='step/start',seq=1,time=2,data=dict(turn=1,step=1)),
        dict(type='request/header',seq=2,time=3,data=dict(header=dict(config=dict(provider='mock',model='mock'),system='system prompt'),reason='initial')),
        dict(type='step/end',seq=3,time=4,data=dict(turn=1,step=1)),
        dict(type='turn/end',seq=4,time=5,data=dict(turn=1,reason=dict(kind='completed')))]
    if version == 2 and seeded:
        events.insert(0,dict(type='session/end-seed',seq=0,time=0,data=dict(inherited=True)))
        for index,event in enumerate(events):event['seq']=index
    return header,events


def fixture(tmp_path, compression, version=2, seeded=False):
    header,events=source_bytes(version,seeded)
    line=lambda value:(json.dumps(value,separators=(',',':'))+'\n').encode('utf-8')
    data=line(header)+b''.join(line(event) for event in events)
    if compression=='zstd':data=compress_frame(line(header))+compress_frame(b''.join(line(event) for event in events))
    path=tmp_path/generationLogFilename(version,compression);path.write_bytes(data)
    return dict(sourcePath=str(path),sourceVersion=version,currentPath=str(tmp_path/generationLogFilename(3,compression)),compression=compression),data


@pytest.mark.asyncio
@pytest.mark.parametrize('compression',['none','zstd'])
@pytest.mark.parametrize('version',[0,1,2])
@pytest.mark.parametrize('seeded',[False,True])
async def test_prepare_then_publish_preserves_source(tmp_path,compression,version,seeded):
    options,original=fixture(tmp_path,compression,version,seeded)
    source=options['sourcePath'];before=os.stat(source)
    prepared=await prepareJsonlMigration(options)
    assert not os.path.exists(options['currentPath'])
    assert prepared.artifact['header']['version']==3
    assert prepared.artifact['header']['isSeeded'] is seeded
    first,second=await asyncio.gather(prepared.publish(),prepared.publish())
    assert first==second
    assert open_read(source)==original
    after=os.stat(source)
    assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns)
    verified=await verifyJsonlCurrentGeneration(options['currentPath'],compression,'generation',len(prepared.artifact['events']))
    assert verified['bytes']==os.path.getsize(options['currentPath'])
    assert not [name for name in os.listdir(tmp_path) if name.endswith('.tmp')]


def open_read(path):
    with open(path,'rb') as stream:return stream.read()


@pytest.mark.asyncio
@pytest.mark.parametrize('compression',['none','zstd'])
async def test_identical_winner_can_append_before_loser_publishes(tmp_path,compression):
    options,_=fixture(tmp_path,compression)
    first=await prepareJsonlMigration(options);second=await prepareJsonlMigration(options)
    await first.publish()
    with open(options['currentPath'],'ab') as stream:
        line=(json.dumps(dict(type='feedback/record',seq=len(first.artifact['events']),time=8,data=dict(text='later')))+'\n').encode('utf-8')
        stream.write(compress_frame(line) if compression=='zstd' else line)
    await second.publish()
    assert not [name for name in os.listdir(tmp_path) if name.endswith('.tmp')]


@pytest.mark.asyncio
@pytest.mark.parametrize('compression',['none','zstd'])
async def test_changed_source_refuses_publication_and_preserves_failure(tmp_path,compression):
    options,_=fixture(tmp_path,compression)
    prepared=await prepareJsonlMigration(options)
    with open(options['sourcePath'],'ab') as stream:stream.write(b'changed')
    for _ in range(2):
        with pytest.raises(JsonlGenerationSourceChangedError):await prepared.publish()
    assert not os.path.exists(options['currentPath'])
    assert not [name for name in os.listdir(tmp_path) if name.endswith('.tmp')]


@pytest.mark.asyncio
async def test_different_winner_is_never_overwritten(tmp_path):
    options,original=fixture(tmp_path,'none')
    prepared=await prepareJsonlMigration(options)
    with open(options['currentPath'],'wb') as stream:stream.write(b'different')
    with pytest.raises(JsonlGenerationTargetConflictError):await prepared.publish()
    assert open_read(options['currentPath'])==b'different'
    assert open_read(options['sourcePath'])==original


@pytest.mark.asyncio
async def test_isolated_verification_must_match_exact_staged_bytes(tmp_path):
    options,_=fixture(tmp_path,'none')
    async def verifier(*args):
        result=await verifyJsonlCurrentGeneration(*args)
        result['digest']='0'*64
        return result
    options['verifyCurrentFile']=verifier
    prepared=await prepareJsonlMigration(options)
    with pytest.raises(ValueError,match='changed during verification'):await prepared.publish()
    assert not os.path.exists(options['currentPath'])
    assert not [name for name in os.listdir(tmp_path) if name.endswith('.tmp')]


@pytest.mark.asyncio
async def test_corrupt_raw_tail_drops_but_committed_turn_refuses(tmp_path):
    options,_=fixture(tmp_path,'none')
    header=dict(type='session',version=2,id='generation',createdAt=1,isSeeded=False,delegationDepth=0)
    data=(json.dumps(header)+'\n{broken\n').encode('utf-8')
    with open(options['sourcePath'],'wb') as stream:stream.write(data)
    prepared=await prepareJsonlMigration(options)
    assert prepared.artifact['events']==[]
    with open(options['sourcePath'],'ab') as stream:stream.write((json.dumps(dict(type='turn/end',seq=0,time=1,data=dict(turn=1,reason=dict(kind='completed'))))+'\n').encode('utf-8'))
    with pytest.raises(ValueError,match='row 1 is not valid JSON'):await prepareJsonlMigration(options)


@pytest.mark.asyncio
async def test_rejects_torn_complete_zstd_record_and_combined_header_frame(tmp_path):
    options,_=fixture(tmp_path,'zstd')
    header,_=source_bytes()
    raw=(json.dumps(header)+'\n').encode('utf-8')
    with open(options['sourcePath'],'wb') as stream:stream.write(compress_frame(raw)+compress_frame(b'{torn'))
    with pytest.raises(ValueError,match='complete frame contains a torn JSONL record'):await prepareJsonlMigration(options)
    with open(options['sourcePath'],'wb') as stream:stream.write(compress_frame(raw+b'{}\n'))
    with pytest.raises(ValueError,match='first frame is not exactly one header line'):await prepareJsonlMigration(options)


@pytest.mark.asyncio
async def test_read_stable_bounds_retries_and_crops_to_second_pre_read_identity():
    metadata=lambda size:dict(dev=1,ino=2,size=size,mtimeNs=size,ctimeNs=size)
    stats=iter([metadata(3),metadata(6),metadata(9)])
    calls=[]
    fs=SimpleNamespace(stat=lambda path:next(stats),readFile=lambda path,signal:(calls.append(path) or b'123456789'))
    result=await createJsonlGenerationRuntime(dict(fs=fs)).readStable('source')
    assert result==dict(bytes=b'123456',identity=metadata(6))
    assert calls==['source','source']


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['write','flush','close','verify','publish'])
@pytest.mark.parametrize('cleanup_failure',[False,True])
async def test_faults_never_publish_and_preserve_primary_and_cleanup_errors(tmp_path,failure,cleanup_failure):
    options,original=fixture(tmp_path,'zstd')
    primary=OSError('injected '+failure)
    cleanup=OSError('injected cleanup')
    class File:
        def __init__(self,file):self.file=file
        def write(self,data):
            if failure=='write':raise primary
            return self.file.write(data)
        def flush(self):
            if failure=='flush':raise primary
            return self.file.flush()
        def fileno(self):return self.file.fileno()
        def close(self):
            self.file.close()
            if failure=='close':raise primary
    class FS(NativeGenerationFileSystem):
        def open(self,*args):return File(super().open(*args))
        def rm(self,path):
            if cleanup_failure:raise cleanup
            return super().rm(path)
    def publish(*args):raise primary
    runtime=createJsonlGenerationRuntime(dict(fs=FS(),**(dict(publishNew=publish) if failure=='publish' else {})))
    async def verify(*args):
        if failure=='verify':raise primary
        return await runtime.verify(*args)
    options['verifyCurrentFile']=verify
    prepared=await runtime.prepare(options)
    with pytest.raises((OSError,GenerationAggregateError)) as raised:await prepared.publish()
    if cleanup_failure:
        assert raised.value.errors==[primary,cleanup]
    else:assert raised.value is primary
    assert not os.path.exists(options['currentPath'])
    assert open_read(options['sourcePath'])==original
    # This is an identified injected cleanup failure, owned by the test.
    for path in tmp_path.glob('*.tmp'):path.unlink()


@pytest.mark.asyncio
async def test_exclusive_stage_name_collision_does_not_modify_existing_stage(tmp_path):
    options,_=fixture(tmp_path,'none')
    old=tmp_path/'session.migration.collision.jsonl.tmp'
    old.write_bytes(b'unrelated crash stage')
    tokens=iter(['collision','new'])
    runtime=createJsonlGenerationRuntime(dict(randomToken=lambda:next(tokens)))
    options['verifyCurrentFile']=runtime.verify
    await (await runtime.prepare(options)).publish()
    assert old.read_bytes()==b'unrelated crash stage'


@pytest.mark.asyncio
async def test_committed_target_survives_post_publication_failure(tmp_path):
    options,_=fixture(tmp_path,'none')
    def barrier(phase,attempt):
        if phase=='after-publication':raise OSError('after commit')
    runtime=createJsonlGenerationRuntime(dict(barrier=barrier))
    options['verifyCurrentFile']=runtime.verify
    prepared=await runtime.prepare(options)
    with pytest.raises(OSError,match='after commit'):await prepared.publish()
    await runtime.verify(options['currentPath'],'none','generation',len(prepared.artifact['events']))


@pytest.mark.asyncio
async def test_caller_cancellation_does_not_abandon_a_prepared_publication(tmp_path):
    options,_=fixture(tmp_path,'none')
    entered,release=asyncio.Event(),asyncio.Event()
    async def verify(*args):
        entered.set()
        await release.wait()
        return await verifyJsonlCurrentGeneration(*args)
    options['verifyCurrentFile']=verify
    prepared=await prepareJsonlMigration(options)
    observer=asyncio.create_task(prepared.publish())
    await entered.wait()
    observer.cancel()
    with pytest.raises(asyncio.CancelledError):await observer
    release.set()
    await prepared.publish()
    assert os.path.isfile(options['currentPath'])


@pytest.mark.asyncio
async def test_async_header_validation_finishes_before_restore_or_writes(tmp_path):
    options,_=fixture(tmp_path,'none')
    observations=[]
    async def validate(header):
        await asyncio.sleep(0)
        observations.append('validated')
    def restore(header):
        assert observations==['validated']
        return default_format_adapter['createRestore'](header)
    options.update(validateHistoricalHeader=validate,format=dict(default_format_adapter,createRestore=restore))
    await prepareJsonlMigration(options)
    assert os.listdir(tmp_path)==['session.v2.jsonl']


@pytest.mark.asyncio
async def test_verifier_runs_in_a_fresh_process_and_rejects_bad_candidate(tmp_path,monkeypatch):
    from dsh.session.generation_verifier import verifyCurrentGenerationInWorker
    options,_=fixture(tmp_path,'none')
    prepared=await prepareJsonlMigration(options)
    await prepared.publish()
    # A contaminated caller cannot replace validation in the fresh interpreter.
    import dsh.session.generation as generation
    async def contaminated(*args):raise AssertionError('parent monkeypatch leaked')
    monkeypatch.setattr(generation,'verifyJsonlCurrentGeneration',contaminated)
    result=await verifyCurrentGenerationInWorker(options['currentPath'],'none','generation',len(prepared.artifact['events']))
    assert result['bytes']==os.path.getsize(options['currentPath'])
    with pytest.raises(ValueError,match='expected "other"'):
        await verifyCurrentGenerationInWorker(options['currentPath'],'none','other',len(prepared.artifact['events']))


@pytest.mark.asyncio
async def test_verifier_queued_abort_never_spawns_and_releases_permits(tmp_path):
    from dsh.core.abort import AbortController
    from dsh.session.generation_verifier import verifyCurrentGenerationInWorker,_permits
    controller=AbortController()
    reason=ValueError('cancel queued verifier')
    _permits.acquire();_permits.acquire()
    try:
        pending=asyncio.create_task(verifyCurrentGenerationInWorker('missing','none','id',0,signal=controller.signal))
        await asyncio.sleep(0)
        controller.abort(reason)
        with pytest.raises(ValueError) as raised:await pending
        assert raised.value is reason
    finally:
        _permits.release();_permits.release()
