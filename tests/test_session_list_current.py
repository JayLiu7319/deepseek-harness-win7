"""Zero-I/O Session summaries, exact search bounds and format-safe cache consumers."""
import asyncio
import json
from pathlib import Path

import pytest

from dsh.api.session_list_current import CurrentSessionList
from dsh.core.abort import AbortController
from dsh.session.canonical_title import SessionTitleService
from dsh.session.projection_cache_current import CurrentSessionProjectionCachePlugin
from dsh.session.projection_cache_current import checkpoint_record
from dsh.storage.hub import StoragePlugin
from dsh.storage.plugins import StorageDomainPlugin, StorageJsonPlugin
from scripts.oracles.session_list_current_python import execute
from scripts.session_format_oracle import json_equal
from tests.test_session_agents_current import api_harness
from tests.test_projection_cache_write_points import settle


CASES = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_list_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_source_list_search_cache_contract(case):
    assert json_equal(execute(case), case['expected'])


@pytest.mark.parametrize('version', [None, True, -1, 1.5, float('inf'), float('nan'), 9007199254740992, '3'])
def test_checkpoint_rejects_invalid_format_generation(version):
    with pytest.raises(ValueError):
        checkpoint_record(dict(identity=dict(createdAt=1, formatVersion=version), rows={}))


async def cache_harness(tmp_path, seed=None):
    ctx, agents = await api_harness(tmp_path)
    await ctx.plugin(SessionTitleService, dict(fallbackMaxWords=5, fallbackMaxBytes=40, maxTitleBytes=80))
    for plugin, config in [(StoragePlugin, {}), (StorageJsonPlugin, dict(root=str(tmp_path/'cache'))), (StorageDomainPlugin, dict(backend='json'))]:
        await ctx.plugin(plugin, config)
    if seed is not None:
        path = tmp_path/'cache/session_projcache/sessions/cold.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(seed), encoding='utf-8')
    await ctx.plugin(CurrentSessionProjectionCachePlugin, dict(writeEveryEvents=100, writeIntervalMs=60000))
    return ctx, agents, CurrentSessionList(ctx)


@pytest.mark.asyncio
async def test_actual_old_cache_lists_title_without_opening_cold_log_then_rebuilds_from_v3(tmp_path, monkeypatch):
    record = dict(identity=dict(createdAt=100, cwd=str(tmp_path), formatVersion=2), rows=dict(
        title=dict(ver=1, seq=99, val='old cached title'),
        sessionListMetadata=dict(ver=1, seq=99, val=dict(blank=True, lastPromptAt=999))))
    ctx, _, listing = await cache_harness(tmp_path, dict(version=6, record=record))
    persistence, cache = ctx.get('sessionPersistence'), ctx.get('sessionProjectionCache')
    writer = await persistence.create(dict(version=3, id='cold', createdAt=100, cwd=str(tmp_path), isSeeded=False))
    await writer.append([dict(seq=0, time=120, type='session/title', data=dict(title='actual title', messageSeqs=[], source=dict(kind='user')))])
    await writer.close()
    original, opened = persistence.open, []
    async def tracking(*args, **kwargs):
        opened.append(args)
        return await original(*args, **kwargs)
    monkeypatch.setattr(persistence, 'open', tracking)
    try:
        rows = await listing.list(AbortController().signal)
        assert len(rows) == 1 and not rows[0]['blank'] and rows[0]['updatedAt'] == 100
        assert rows[0]['projections'] == dict(asOfSeq=-1, values=dict(title='old cached title'))
        assert not opened and ctx.get('sessions').get('cold') is None
        observed = await ctx.get('sessionQuery').observeSession('cold')
        try:
            assert observed.projections['values']['title'] == 'actual title'
            assert observed.projections['values']['sessionListMetadata'] == dict(blank=True, lastPromptAt=None)
        finally:
            observed.dispose()
        assert len(opened) == 1 and ctx.get('sessions').get('cold') is None
        # Prepared hydration deliberately does not write a possibly repaired log cut.
        rows_header = (await ctx.get('sessionQuery').listSessions())[0]['header']
        assert cache.cachedPredecessorTitle(rows_header, 0)['values']['title'] == 'old cached title'
        assert cache.cachedSnapshot(rows_header, 0) is None
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_actual_v7_checkpoint_format_cut_and_reopen(tmp_path):
    ctx, agents, listing = await cache_harness(tmp_path)
    try:
        agent = await agents.ensureSession('warm', str(tmp_path), False)
        agent.session.append('turn/start', dict(turn=1))
        ctx.get('sessionTitle').rename(agent.session, 'warm title')
        cache = ctx.get('sessionProjectionCache')
        await settle(cache)
        await cache.write(agent.session)
        header = agent.session.header
        snapshot = cache.cachedSnapshot(header, 0)
        assert snapshot['values']['title'] == 'warm title'
        assert snapshot['values']['sessionListMetadata']['blank'] is False
    finally:
        await ctx.fiber.dispose()
    path = tmp_path/'cache/session_projcache/sessions/warm.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    assert record['version'] == 7 and record['record']['identity']['formatVersion'] == 3
    fresh, _, listing = await cache_harness(tmp_path)
    try:
        restored = fresh.get('sessionProjectionCache').cachedSnapshot(header, 0)
        assert restored is not None and restored['values']['title'] == 'warm title'
        assert fresh.get('sessions').get('warm') is None
    finally:
        await fresh.fiber.dispose()


@pytest.mark.asyncio
async def test_actual_current_sqlite_search_respects_live_current_surface(tmp_path):
    from dsh.session.query_current import CurrentSqliteSessionQueryEngine
    ctx, agents, listing = await cache_harness(tmp_path)
    query = CurrentSqliteSessionQueryEngine(ctx, dict(path=':memory:'))
    ctx.set_service('sessionQuery', query)
    await query.initialize()
    try:
        agent = await agents.ensureSession('visible', str(tmp_path), False)
        message = dict(id='one', role='user', content=[dict(type='text', text='needle in current surface')], source=dict(kind='user'))
        agent.session.append('user/message', message, surface_op='append')
        result = await listing.search('needle', AbortController().signal)
        assert [item['sessionId'] for item in result['items']] == ['visible']
        assert result['hasMore'] is False
        assert not any(other.id != 'visible' for other in ctx.get('agents').list())
    finally:
        await settle(ctx.get('sessionProjectionCache'))
        await ctx.fiber.dispose()
