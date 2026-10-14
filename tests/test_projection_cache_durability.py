import asyncio
import json

import pytest

from dsh.cordis.context import Context
from dsh.core.session.session import SessionPlugin
from dsh.session.projections import SessionProjectionsPlugin
from dsh.session.projection_cache import SessionProjectionCachePlugin
from dsh.storage.hub import StoragePlugin
from dsh.storage.plugins import StorageJsonPlugin, StorageDomainPlugin


async def composition(root):
    ctx = Context()
    await ctx.plugin(SessionPlugin)
    await ctx.plugin(SessionProjectionsPlugin)
    await ctx.plugin(StoragePlugin)
    await ctx.plugin(StorageJsonPlugin, config={"root": str(root)})
    await ctx.plugin(StorageDomainPlugin, config={"backend": "json"})
    ctx.get("sessionProjections").register({"key": "count", "stateVersion": 1,
        "stateSchema": lambda value: int(value), "init": lambda header, inherited_event_count: 0,
        "apply": lambda state, event: state + 1, "wire": {"viewSchema": lambda value: int(value), "view": lambda state: state}})
    await ctx.plugin(SessionProjectionCachePlugin, config={"writeEveryEvents": 10, "writeIntervalMs": 5000})
    return ctx


@pytest.mark.asyncio
async def test_checkpoint_reopens_and_recreated_identity_does_not_reuse_it(tmp_path):
    ctx = await composition(tmp_path)
    sessions = ctx.get("sessions")
    session = sessions.create("cache-session", meta={"cwd": str(tmp_path)})
    session.append("test/event", {"value": 1}, ignorable=True)
    cache = ctx.get("sessionProjectionCache")
    await cache.write(session)
    expected = cache.cached_snapshot(session.header, session.inheritedEventCount)
    assert expected["values"]["count"] == len(session.events)
    document = tmp_path / "session_projcache" / "sessions" / "cache-session.json"
    assert json.loads(document.read_text(encoding="utf-8"))["version"] == 5
    header = session.header
    await ctx.fiber.dispose()
    fresh = await composition(tmp_path)
    try:
        assert fresh.get("sessionProjectionCache").cached_snapshot(header, 0) == expected
        from dsh.core.session import SessionHeader
        replacement = SessionHeader("cache-session", created_at=header.createdAt + 1, cwd=header.cwd)
        assert fresh.get("sessionProjectionCache").cached_snapshot(replacement, 0) is None
    finally:
        await fresh.fiber.dispose()


@pytest.mark.asyncio
async def test_stale_per_record_file_does_not_hide_other_records(tmp_path):
    from dsh.storage.storage_json import JsonStorageBackend
    from dsh.storage.backend import KvUnitDescriptor
    backend = JsonStorageBackend(str(tmp_path))
    unit = await backend.kv.open(KvUnitDescriptor("cache", 4, ["sessions"], layout="per-record"))
    await unit.put_record("sessions", "good", {"value": 1})
    (tmp_path / "cache" / "sessions" / "stale.json").write_text('{"version":3,"record":42}', encoding="utf-8")
    (tmp_path / "cache" / "sessions" / "bad.json").write_text('{broken', encoding="utf-8")
    assert (await unit.load_all())["tables"] == {"sessions": {"good": {"value": 1}}}
    with pytest.raises(ValueError, match="path-safe"):
        await unit.put_record("sessions", "../escape", 1)
    await backend.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("document", [
    {"unit": None, "tables": {}},
    {"unit": {"name": "cache"}, "tables": ["invalid"]},
    {"unit": {"name": "foreign"}, "tables": {"sessions": {"one": 1}}},
])
async def test_invalid_legacy_cache_is_ignored_and_preserved(tmp_path, document):
    from dsh.storage.storage_json import JsonStorageBackend
    from dsh.storage.backend import KvUnitDescriptor
    path = tmp_path / "cache.json"
    original = json.dumps(document)
    path.write_text(original, encoding="utf-8")
    backend = JsonStorageBackend(str(tmp_path))
    try:
        unit = await backend.kv.open(KvUnitDescriptor("cache", 4, ["sessions"], layout="per-record"))
        assert (await unit.load_all())["tables"] == {"sessions": {}}
        assert path.read_text(encoding="utf-8") == original
        assert not (tmp_path / "cache").exists()
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_cold_session_listing_survives_restart_without_activating_agent(tmp_path):
    from dsh.session.persistence_jsonl_canonical import JsonlSessionPersistencePlugin
    from dsh.session.listing import SessionListing
    first = await composition(tmp_path / "storage")
    await first.plugin(JsonlSessionPersistencePlugin, config={"root": str(tmp_path / "logs")})
    listing = SessionListing(first)
    session = first.get("sessions").create("stored-session", meta={"cwd": str(tmp_path)})
    session.append("turn/start", {"turn": 1})
    session.append_user_message("hello")
    await first.get("sessionProjectionCache").write(session)
    before = await listing.list()
    assert before[0]["blank"] is False
    await first.fiber.dispose()
    fresh = await composition(tmp_path / "storage")
    await fresh.plugin(JsonlSessionPersistencePlugin, config={"root": str(tmp_path / "logs")})
    try:
        after = await SessionListing(fresh).list()
        assert after == before
        assert fresh.get("sessions").get("stored-session") is None
        assert fresh.get("agents") is None
    finally:
        await fresh.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('version', [3, 4])
async def test_prior_checkpoint_reuses_only_unseeded_identity(tmp_path, version):
    from dsh.core.session import SessionHeader
    directory = tmp_path / 'session_projcache' / 'sessions'
    directory.mkdir(parents=True)
    record = dict(identity=dict(createdAt=1), rows=dict(count=dict(ver=1, seq=7, val=8)))
    (directory / 'old.json').write_text(json.dumps(dict(version=version, record=record)), encoding='utf-8')
    ctx = await composition(tmp_path)
    try:
        cache = ctx.get('sessionProjectionCache')
        assert cache.cached_snapshot(SessionHeader('old', created_at=1), 0)['values']['count'] == 8
        assert cache.cached_snapshot(SessionHeader('old', created_at=1, is_seeded=True), 0) is None
        assert cache.cached_snapshot(SessionHeader('old', created_at=1, is_seeded=True), 2) is None
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
async def test_seeded_checkpoint_requires_exact_cut_and_invalid_record_is_backed_up(tmp_path):
    from dsh.core.session import SessionHeader
    directory = tmp_path / 'session_projcache' / 'sessions'
    directory.mkdir(parents=True)
    record = dict(identity=dict(createdAt=1, isSeeded=True, inheritedEventCount=2),
                  rows=dict(count=dict(ver=1, seq=7, val=8)))
    (directory / 'seeded.json').write_text(json.dumps(dict(version=5, record=record)), encoding='utf-8')
    broken = directory / 'broken.json'
    raw = json.dumps(dict(version=5, record=dict(identity=None, rows={})))
    broken.write_text(raw, encoding='utf-8')
    ctx = await composition(tmp_path)
    try:
        cache = ctx.get('sessionProjectionCache')
        header = SessionHeader('seeded', created_at=1, is_seeded=True)
        assert cache.cached_snapshot(header, 2)['values']['count'] == 8
        assert cache.cached_snapshot(header, 0) is None
        assert cache.cached_snapshot(header, 1) is None
        assert not broken.exists()
        backups = list(directory.glob('broken.json.bak.*'))
        assert len(backups) == 1 and backups[0].read_text(encoding='utf-8') == raw
    finally:
        await ctx.fiber.dispose()

