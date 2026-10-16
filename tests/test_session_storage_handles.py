"""Actual Source observations plus cancellation, batching and effect ownership."""
import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsh.core.session.json import FrozenDict
from dsh.session.jsonl_handle import JsonlSessionHandle, JsonlBackendTracker, StorageAggregateError
from dsh.session.persistence import SessionAlreadyOwnedError, SessionFormatUnsupportedError, SessionHandleClosedError
from dsh.session.storage_contract import validateStoredEvents, materializeAppendBatch
from scripts.oracles.session_format_python import observe
from scripts.session_format_oracle import json_equal

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/session_storage_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=[case['case'] for case in CASES])
def test_actual_source_storage_observation(case):
    assert json_equal(observe(case),dict(case=case['case'],outcome='value',value=case['expected']))


def event(seq=0):
    return dict(type='turn/start',seq=seq,time=1,data=dict(turn=1))


class Storage:
    def __init__(self):
        self.tracker=JsonlBackendTracker('native')
        self.events=[]
        self.entered=asyncio.Event()
        self.resume=asyncio.Event();self.resume.set()
        self.failures=0
        self.release_failure=None
        self.release_count=0
        self.lease_count=0
        self.batches=[]

    def create(self,session_id='s'):
        header=dict(version=3,id=session_id,createdAt=1,isSeeded=False)
        self.tracker.registerCreated(header,0)
        return self.tracker.adopt(JsonlSessionHandle(self,session_id,header,'write',dict(cursor=0,materialized=False,inheritedEventCount=0)))

    async def acquireWriteLease(self,header):
        self.lease_count+=1
        return self

    async def release(self):
        self.release_count+=1
        if self.release_failure:raise self.release_failure

    async def persistBatch(self,header,events,materialized,cut):
        self.entered.set();await self.resume.wait()
        if self.failures:
            self.failures-=1
            raise OSError('write failed')
        self.batches.append(copy.deepcopy(events));self.events.extend(events)
        self.tracker.materialized(header['id'])

    async def persistHeader(self,header,cut):
        self.tracker.materialized(header['id'])

    def releaseHandle(self,handle,materialized):
        self.tracker.release(handle,materialized)


@pytest.mark.asyncio
async def test_cancelled_append_observer_still_commits_detached_batch_before_next_mutation():
    storage=Storage();storage.resume.clear();handle=storage.create()
    batch=[event()];first=handle.append(batch);batch[0]['data']['turn']=99
    await storage.entered.wait();first.cancel()
    with pytest.raises(asyncio.CancelledError):await first
    second=handle.append([event(1)]);storage.resume.set();await second
    assert [e['seq'] for e in storage.events]==[0,1]
    assert storage.events[0]['data']['turn']==1
    await handle.close();assert storage.release_count==1


@pytest.mark.asyncio
async def test_cancelled_close_observer_joins_same_drain_and_releases_once():
    storage=Storage();storage.resume.clear();handle=storage.create()
    handle.enqueueLive(event(),lambda error:None)
    close=handle.close();await storage.entered.wait();close.cancel()
    with pytest.raises(asyncio.CancelledError):await close
    with pytest.raises(SessionHandleClosedError):await handle.append([])
    storage.resume.set();await handle.close();await handle.close()
    assert len(storage.events)==1 and storage.release_count==1
    storage.tracker.claimWrite('s')


@pytest.mark.asyncio
async def test_cancelled_drain_observer_does_not_splice_or_duplicate_other_observer_batch():
    storage=Storage();storage.resume.clear();handle=storage.create()
    handle.enqueueLive(event(),lambda error:None)
    first=handle.drainLive();second=handle.drainLive();await storage.entered.wait();first.cancel()
    storage.resume.set();await second
    assert len(storage.batches)==1 and len(storage.events)==1
    await handle.close()


@pytest.mark.asyncio
async def test_close_redrains_events_published_while_first_write_is_blocked():
    storage=Storage();storage.resume.clear();handle=storage.create()
    original=event();handle.enqueueLive(original,lambda error:None);original['data']['turn']=99
    close=handle.close();await storage.entered.wait()
    handle.enqueueLive(event(1),lambda error:None);storage.resume.set();await close
    assert [e['seq'] for e in storage.events]==[0,1]
    assert storage.events[0]['data']['turn']==1 and not handle.buffered


@pytest.mark.asyncio
async def test_deadline_failure_pauses_timer_and_retains_order_for_explicit_retry():
    storage=Storage();storage.failures=1;handle=storage.create()
    observed=asyncio.get_running_loop().create_future()
    handle.enqueueLive(event(),lambda error:observed.set_result(error))
    error=await asyncio.wait_for(observed,2)
    assert str(error)=='write failed' and handle.drainPaused
    handle.enqueueLive(event(1),lambda error:pytest.fail('retry must be explicit'))
    assert handle.batchTimer is None
    await handle.drainLive();assert [e['seq'] for e in storage.events]==[0,1]
    await handle.close()


@pytest.mark.asyncio
async def test_close_aggregate_keeps_both_failures_and_always_releases_process_claim():
    storage=Storage();storage.failures=1;storage.release_failure=OSError('release failed');handle=storage.create()
    handle.enqueueLive(event(),lambda error:None)
    with pytest.raises(StorageAggregateError) as failure:await handle.close()
    assert [str(e) for e in failure.value.errors]==['write failed','release failed']
    assert not storage.tracker.openHandles and not storage.tracker.hasPending('s')
    storage.tracker.claimWrite('s')
    with pytest.raises(StorageAggregateError) as again:await handle.close()
    assert again.value is failure.value and storage.release_count==1


@pytest.mark.asyncio
async def test_unflushed_empty_session_never_materializes_but_flush_is_a_durability_barrier():
    storage=Storage();handle=storage.create();await handle.close()
    assert storage.lease_count==0 and not storage.tracker.hasPending('s')
    handle=storage.create();await handle.flush()
    assert storage.lease_count==1 and not storage.tracker.hasPending('s')
    await handle.close()


@pytest.mark.asyncio
async def test_tracker_flush_continues_other_writers_and_dispose_aggregates():
    tracker=JsonlBackendTracker('batch');calls=[]
    class Writer:
        access='write'
        def __init__(self,session_id):self.id=session_id
        async def drainLive(self):calls.append(('drain',self.id))
        async def flush(self):
            calls.append(('flush',self.id))
            if self.id=='a':raise OSError('a flush')
        async def close(self):
            calls.append(('close',self.id));tracker.release(self,True)
            raise OSError(self.id+' close')
    tracker.adopt(Writer('a'));tracker.adopt(Writer('b'))
    with pytest.raises(StorageAggregateError) as flush:await tracker.flushAll()
    assert str(flush.value)=='batch flush failed'
    assert calls==[('drain','a'),('flush','a'),('drain','b'),('flush','b')]
    with pytest.raises(StorageAggregateError) as dispose:await tracker.dispose()
    assert [str(e) for e in dispose.value.errors]==['a close','b close'] and not tracker.openHandles


@pytest.mark.asyncio
async def test_abort_waiting_mutation_is_observed_at_queue_entry_without_releasing_owner():
    from dsh.core.abort import AbortController
    storage=Storage();storage.resume.clear();handle=storage.create()
    first=handle.append([event()]);await storage.entered.wait()
    controller=AbortController();reason=OSError('queued abort')
    second=handle.append([event(1)],dict(signal=controller.signal))
    controller.abort(reason);storage.resume.set();await first
    with pytest.raises(OSError) as refusal:await second
    assert refusal.value is reason and storage.release_count==0
    with pytest.raises(SessionAlreadyOwnedError):storage.tracker.claimWrite('s')
    await handle.append([event(1)]);await handle.close()


@pytest.mark.asyncio
async def test_abort_after_write_starts_does_not_interrupt_durability():
    from dsh.core.abort import AbortController
    storage=Storage();storage.resume.clear();handle=storage.create();controller=AbortController()
    pending=handle.append([event()],dict(signal=controller.signal));await storage.entered.wait()
    controller.abort(OSError('late abort'));storage.resume.set();await pending
    assert len(storage.events)==1
    await handle.close()


@pytest.mark.asyncio
async def test_cordis_owned_routing_does_not_autocreate_and_dispose_releases_every_handle():
    from dsh.cordis import Context
    root=Context();storage=Storage()
    # Create a real owning fiber, so event registrations and cleanup are reversible.
    class Provider:
        name='handle-routing'
        def apply(self,ctx):storage.tracker.install(ctx)
    fiber=root.plugin(Provider())
    await fiber
    root.emit('session/event',SimpleNamespace(id='unowned'),event())
    assert not storage.tracker.pending
    handle=storage.create();root.emit('session/event',SimpleNamespace(id='s'),event())
    await root.parallel('session/flush',SimpleNamespace(id='s'))
    assert len(storage.events)==1
    await fiber.dispose()
    assert not storage.tracker.openHandles and storage.release_count==1
    root.emit('session/event',SimpleNamespace(id='s'),event(1))
    assert not handle.buffered
    await root.fiber.dispose()


def test_storage_vocabulary_precedes_any_freezing_and_freezes_only_identified_message():
    user=dict(type='user/message',seq=0,time=1,surfaceOp='append',data=dict(id='u',role='user',content=[],source=dict(kind='user')))
    events=[user,dict(type='future',seq=1,time=2,data={})]
    with pytest.raises(SessionFormatUnsupportedError):validateStoredEvents(dict(id='s'),events)
    assert not isinstance(user['data'],FrozenDict)
    events.pop();assert validateStoredEvents(dict(id='s'),events) is events
    assert isinstance(user['data'],FrozenDict) and not isinstance(user,FrozenDict)


def test_lossless_batch_refuses_cycles_without_reading_accessors():
    cycle={};cycle['self']=cycle
    with pytest.raises(TypeError):materializeAppendBatch([cycle])
    class Accessor:
        @property
        def data(self):pytest.fail('must not execute accessors during snapshot')
    with pytest.raises(TypeError):materializeAppendBatch([Accessor()])
