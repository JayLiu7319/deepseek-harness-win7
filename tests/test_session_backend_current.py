"""Actual Source filesystem observations and native transaction/cancellation tests."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.core.abort import AbortController
from dsh.core.session.json import FrozenDict, UNDEFINED
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistence, CurrentJsonlSessionPersistencePlugin
from dsh.session.jsonl_current import generationLogPath, eventLines
from dsh.session.jsonl_zstd import compress_frame
from dsh.session.persistence import SessionAlreadyOwnedError
from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'scripts/oracles/session_backend_cases.json').read_text(encoding='utf8'))


@pytest.mark.parametrize('case',CASES,ids=[case['case'] for case in CASES])
def test_actual_source_backend_filesystem_journey(case):
    assert json_equal(observe(case),dict(case=case['case'],outcome='value',value=case['expected']))


def header(session_id='generation'):
    return dict(version=3,id=session_id,createdAt=1,isSeeded=False)


def event(seq=0):
    return dict(type='turn/start',seq=seq,time=1,data=dict(turn=1))


@pytest.fixture(params=['none','zstd'])
def backend(tmp_path,request):
    return CurrentJsonlSessionPersistence(str(tmp_path/'sessions'),request.param)


def history(backend,version=2):
    cases=json.loads((ROOT/'scripts/oracles/session_generation_cases.json').read_text(encoding='utf8'))
    raw=next(c['raw'] for c in cases if c['case']=='generation/none/v%s/publish'%version)
    path=Path(generationLogPath(backend.root,UNDEFINED,'generation',version,backend.compression))
    path.parent.mkdir(parents=True,exist_ok=True)
    if backend.compression=='none':data=raw.encode('utf8')
    else:
        first,body=raw.split('\n',1);data=compress_frame((first+'\n').encode('utf8'))+compress_frame(body.encode('utf8'))
    path.write_bytes(data)
    return path


async def until(predicate):
    async def wait():
        while not predicate():await asyncio.sleep(0)
    await asyncio.wait_for(wait(),3)


@pytest.mark.asyncio
async def test_created_handle_detaches_header_immediately_and_has_no_filesystem_footprint(backend):
    meta=header();pending=backend.create(meta);meta['createdAt']=99
    handle=await pending
    assert not Path(backend.root).exists()
    assert (await backend.stat('generation'))['header']['createdAt']==1
    await handle.close();assert not Path(backend.root).exists()


@pytest.mark.asyncio
async def test_empty_id_lookup_only_encodes_when_a_project_directory_exists(backend):
    # Actual Source findLog iterates projects before encoding the lookup id.
    assert await backend.stat('') is None
    Path(backend.root).mkdir()
    assert await backend.stat('') is None
    (Path(backend.root) / 'project').mkdir()
    with pytest.raises(ValueError, match='cannot encode an empty path segment'):
        await backend.stat('')
    await backend.close()


@pytest.mark.asyncio
async def test_single_shared_root_encoding_probe_precedes_concurrent_create(backend,monkeypatch):
    import threading
    entered=threading.Event();resume=threading.Event();calls=[]
    original=backend._ensure_encoding
    def check():
        calls.append(1);entered.set();assert resume.wait(3);original()
    monkeypatch.setattr(backend,'_ensure_encoding',check)
    first=backend.create(header('a'));second=backend.create(header('b'))
    await until(entered.is_set)
    assert not first.done() and not second.done()
    resume.set();a,b=await asyncio.gather(first,second)
    assert len(calls)==1
    await a.close();await b.close()


@pytest.mark.asyncio
async def test_cold_memo_reuses_shared_frozen_events_and_invalidates_after_local_append(backend,monkeypatch):
    handle=await backend.create(header());await handle.append([event()]);await handle.close()
    import dsh.session.jsonl_backend_current as module
    actual=module.readStableJsonlFile;reads=[]
    async def read(*args,**kwargs):reads.append(args[0]);return await actual(*args,**kwargs)
    monkeypatch.setattr(module,'readStableJsonlFile',read)
    reader=await backend.open('generation','read');first=await reader.read();again=await reader.read()
    assert first['events'] is not again['events'] and first['events'][0] is again['events'][0]
    assert isinstance(first['events'][0],FrozenDict) and len(reads)==1
    writer=await backend.open('generation','write');assert len(reads)==1
    await writer.append([dict(type='turn/end',seq=1,time=2,data=dict(turn=1,reason=dict(kind='completed'))) ])
    assert len((await reader.read())['events'])==2 and len(reads)==2
    await backend.close()


@pytest.mark.asyncio
async def test_metadata_calls_never_decode_body_and_historical_reads_never_publish(backend,monkeypatch):
    path=history(backend);original=path.read_bytes()
    assert (await backend.stat('generation'))['header']['version']==3
    assert len(await backend.list())==1 and path.read_bytes()==original
    reader=await backend.open('generation','read');read=await reader.read()
    assert read['events'] and read['eventState']=='shared-frozen'
    assert path.read_bytes()==original and not Path(backend.locate(header())).exists()
    await backend.close()


@pytest.mark.asyncio
async def test_shared_migration_one_waiter_abort_keeps_other_waiter_and_original_reason(backend,monkeypatch):
    history(backend);entered=asyncio.Event();resume=asyncio.Event();calls=[];owner=[]
    actual=backend._prepare_migration
    async def prepare(session_id,selected,signal):
        calls.append(1);owner.append(signal);entered.set();await resume.wait()
        return await actual(session_id,selected,signal)
    monkeypatch.setattr(backend,'_prepare_migration',prepare)
    controller=AbortController();reason=OSError('one waiter cancelled')
    first=asyncio.create_task(backend.open('generation','read',dict(signal=controller.signal)))
    await entered.wait();second=asyncio.create_task(backend.open('generation','read'))
    await until(lambda:backend.migrationPreparations['generation']['waiters']==2)
    controller.abort(reason)
    with pytest.raises(OSError) as failed:await first
    assert failed.value is reason and not owner[0].aborted
    resume.set();handle=await second;assert len(calls)==1
    await handle.close();await backend.close()


@pytest.mark.asyncio
async def test_last_migration_waiter_abort_cancels_owned_work_and_next_open_reprepares(backend,monkeypatch):
    history(backend);entered=asyncio.Event();resume=asyncio.Event();calls=[];owners=[]
    actual=backend._prepare_migration
    async def prepare(session_id,selected,signal):
        calls.append(1);owners.append(signal);entered.set();await resume.wait()
        return await actual(session_id,selected,signal)
    monkeypatch.setattr(backend,'_prepare_migration',prepare)
    controller=AbortController();pending=asyncio.create_task(backend.open('generation','read',dict(signal=controller.signal)))
    await entered.wait();controller.abort('last waiter left')
    with pytest.raises(ValueError,match='session migration preparation aborted') as failure:await pending
    assert failure.value.cause=='last waiter left' and owners[0].aborted
    assert not backend.migrationPreparations
    resume.set();reader=await backend.open('generation','read')
    assert len(calls)==2
    await reader.close();await backend.close()


@pytest.mark.asyncio
async def test_python_cancel_during_publication_keeps_lease_until_commit_and_closes_unclaimed_handle(backend,monkeypatch):
    path=history(backend);original=path.read_bytes();entered=asyncio.Event();resume=asyncio.Event()
    actual=backend.publishStoredMigration
    async def publish(session_id,stored):
        entered.set();await resume.wait();return await actual(session_id,stored)
    monkeypatch.setattr(backend,'publishStoredMigration',publish)
    pending=asyncio.create_task(backend.open('generation','write'));await entered.wait();pending.cancel()
    foreign=CurrentJsonlSessionPersistence(backend.root,backend.compression)
    with pytest.raises(SessionAlreadyOwnedError):await foreign.open('generation','write')
    resume.set()
    with pytest.raises(asyncio.CancelledError):await pending
    assert path.read_bytes()==original and Path(backend.locate(header())).exists()
    assert not backend.tracker.openHandles
    writer=await foreign.open('generation','write');await writer.close();await backend.close();await foreign.close()


@pytest.mark.asyncio
async def test_signal_abort_during_publication_is_refused_after_successful_commit(backend,monkeypatch):
    history(backend);entered=asyncio.Event();resume=asyncio.Event();controller=AbortController()
    actual=backend.publishStoredMigration
    async def publish(session_id,stored):entered.set();await resume.wait();return await actual(session_id,stored)
    monkeypatch.setattr(backend,'publishStoredMigration',publish)
    pending=asyncio.create_task(backend.open('generation','write',dict(signal=controller.signal)))
    await entered.wait();reason=OSError('publication observer aborted');controller.abort(reason);resume.set()
    with pytest.raises(OSError) as failure:await pending
    assert failure.value is reason and Path(backend.locate(header())).exists()
    writer=await backend.open('generation','write');await writer.close();await backend.close()


@pytest.mark.asyncio
async def test_actual_append_sync_failure_rolls_back_original_bytes_and_cursor_retries(backend,monkeypatch):
    writer=await backend.create(header());await writer.append([event()]);path=Path(backend.locate(header()));original=path.read_bytes()
    actual=os.fsync;calls=[]
    def sync(fd):
        calls.append(1)
        if len(calls)==1:raise OSError('injected sync failure')
        return actual(fd)
    monkeypatch.setattr(os,'fsync',sync)
    end=dict(type='turn/end',seq=1,time=2,data=dict(turn=1,reason=dict(kind='completed')))
    with pytest.raises(OSError,match='injected sync failure'):await writer.append([end])
    assert path.read_bytes()==original and writer.state['cursor']==1
    await writer.append([end]);assert len((await writer.read())['events'])==2
    await backend.close()


@pytest.mark.asyncio
async def test_torn_tail_complete_events_rewrite_before_new_append_and_read_only_does_not_touch(tmp_path):
    backend=CurrentJsonlSessionPersistence(str(tmp_path/'sessions'),'zstd')
    writer=await backend.create(header());await writer.append([event()]);await writer.close()
    end=dict(type='turn/end',seq=1,time=2,data=dict(turn=1,reason=dict(kind='completed')))
    path=Path(backend.locate(header()))
    with path.open('ab') as stream:stream.write(compress_frame((eventLines([end])+'\n').encode('utf8'))[:-2])
    before=path.read_bytes();reader=await backend.open('generation','read')
    assert len((await reader.read())['events'])==2 and path.read_bytes()==before
    writer=await backend.open('generation','write');await writer.append([dict(type='session/end-seed',seq=2,time=3,data={})])
    assert len((await reader.read())['events'])==3 and writer.state['cursor']==3
    assert not writer.state.get('recoveredTail')
    await backend.close()


@pytest.mark.asyncio
async def test_current_backend_mount_has_no_session_service_dependency_and_owned_teardown(tmp_path):
    from dsh.cordis import Context
    root=Context();fiber=await root.plugin(CurrentJsonlSessionPersistencePlugin,dict(root=str(tmp_path/'sessions'),compression='none'))
    backend=root.get('sessionPersistence');writer=await backend.create(header())
    root.emit('session/event',SimpleNamespace(id='generation'),event())
    await fiber.dispose()
    assert not backend.tracker.openHandles and Path(backend.locate(header())).exists()
    assert root.get('sessionPersistence') is None
    fresh=CurrentJsonlSessionPersistence(backend.root,'none');reader=await fresh.open('generation','read')
    assert len((await reader.read())['events'])==1
    await fresh.close();await root.fiber.dispose()
