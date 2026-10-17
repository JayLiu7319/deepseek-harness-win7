"""Disposable, identity-bound projection checkpoints over storageDomain."""
import asyncio
import copy
import logging

from dsh.cordis.plugin import Plugin
from dsh.cordis.awaiting import start_coroutine
from dsh.core.session import snapshot_json_value
from dsh.core.session.types import SessionLogOffset, _is_safe_non_negative_int
from dsh.storage.domain_spec import define_domain, domain_table


def _record(value):
    if not isinstance(value, dict) or not isinstance(value.get("identity"), dict) or not isinstance(value.get("rows"), dict):
        raise ValueError("invalid projection checkpoint record")
    identity = value["identity"]
    if not _is_safe_non_negative_int(identity.get('createdAt')):
        raise ValueError("invalid checkpoint identity")
    if "cwd" in identity and not isinstance(identity["cwd"], str):
        raise ValueError("invalid checkpoint cwd")
    if 'isSeeded' in identity and type(identity['isSeeded']) is not bool:
        raise ValueError('invalid checkpoint lineage')
    if 'inheritedEventCount' in identity:
        SessionLogOffset(identity['inheritedEventCount'])
    for row in value["rows"].values():
        if not isinstance(row, dict) or "val" not in row:
            raise ValueError("invalid checkpoint row")
        if not _is_safe_non_negative_int(row.get('ver')):
            raise ValueError('invalid checkpoint row')
        if type(row.get('seq')) not in (int, float) or row['seq'] != -1:
            SessionLogOffset(row.get('seq'))
    # snapshot_json_value rejects values outside the session JSON vocabulary.
    if snapshot_json_value(value) is None:
        raise ValueError("checkpoint is not losslessly JSON-serializable")
    return copy.deepcopy(value)


PROJECTION_CACHE_SPEC = define_domain({"name": "session_projcache", "version": 5,
    "compatibleVersions": [3, 4], "invalidRecords": "backup-and-skip",
    "layout": "per-record", "tables": {"sessions": domain_table(_record)}})


def _identity(header, inherited_event_count):
    cut = SessionLogOffset(inherited_event_count)
    if not header.isSeeded and cut != 0:
        raise ValueError('unseeded projection-cache identity inherited event count must be 0')
    result = {"createdAt": header.createdAt, "isSeeded": header.isSeeded,
              "inheritedEventCount": cut}
    if header.cwd is not None:
        result["cwd"] = header.cwd
    return result


class SessionProjectionCache:
    def __init__(self, ctx, table, config):
        self.ctx, self.table, self.config = ctx, table, config
        self.dirty, self.tasks = {}, set()
        self.writes = {}
        self.closed = False

    def _rows(self, header, inherited_event_count):
        record = self.table.get(header.id)
        identity = dict(record['identity']) if record else {}
        identity.setdefault('isSeeded', False)
        identity.setdefault('inheritedEventCount', 0)
        return record["rows"] if record and identity == _identity(header, inherited_event_count) else {}

    def cached_snapshot(self, header, inherited_event_count, keys=None):
        rows = self._rows(header, inherited_event_count)
        values = self.ctx.get("sessionProjections").view_checkpoint(rows, keys)
        if not values:
            return None
        return {"asOfSeq": min(rows[key]["seq"] for key in values), "values": values}

    cachedSnapshot = cached_snapshot

    def hydrate_prepared(self, session, events):
        projections = self.ctx.get("sessionProjections")
        try:
            return projections.hydrate(session, self._rows(session.header, session.inheritedEventCount), events, 0)
        except Exception:
            return projections.hydrate(session, {}, events, 0)

    hydratePrepared = hydrate_prepared

    def cold_snapshot(self, meta, inherited_event_count, events):
        projections = self.ctx.get("sessionProjections")
        restored = projections.restore(self._rows(meta, inherited_event_count), events, 0, meta,
                                       inherited_event_count)
        self._schedule(self._put(meta, inherited_event_count, restored["checkpoint"]))
        return restored["snapshot"]

    coldSnapshot = cold_snapshot

    def _clean(self, session):
        state = self.dirty.pop(session, None)
        if state and state[1] is not None:
            state[1].cancel()

    async def _put(self, header, inherited_event_count, rows):
        await self.table.put(header.id, _record({"identity": _identity(header, inherited_event_count), "rows": rows}))

    def write(self, session):
        # JS async functions capture this cut and reset the counter at call time.
        try:
            rows = self.ctx.get("sessionProjections").checkpoint(session)
            self._clean(session)
            sessions = self.ctx.get("sessions")
            live = sessions.get(session.id) is session
        except Exception as error:
            async def failed(reason=error):
                raise reason
            return asyncio.create_task(failed())

        async def commit():
            if live:
                await sessions.flush(session)
            await self._put(session.header, session.inheritedEventCount, rows)

        # Enter the event loop at call time so an explicitly awaited write
        # cannot overtake an earlier fire-and-forget creation checkpoint.
        pending = start_coroutine(commit())
        writes = self.writes.setdefault(session, set())
        writes.add(pending)
        def settled(job):
            writes.discard(job)
            if not writes and self.writes.get(session) is writes:
                self.writes.pop(session, None)
        pending.add_done_callback(settled)
        return pending

    def _schedule(self, coroutine):
        if self.closed:
            if asyncio.isfuture(coroutine):
                coroutine.cancel()
            else:
                coroutine.close()
            return

        async def soft():
            try:
                await coroutine
            except Exception as error:
                logging.getLogger("session-projection-cache").warning("Checkpoint write failed: %s", error)

        task = asyncio.create_task(soft())
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def event(self, session, event):
        if self.closed:
            return
        if event["type"] == "turn/end":
            self._schedule(self.write(session))
            return
        state = self.dirty.setdefault(session, [0, None])
        state[0] += 1
        if state[0] >= self.config["writeEveryEvents"]:
            self._schedule(self.write(session))
        elif state[1] is None:
            state[1] = asyncio.get_running_loop().call_later(
                self.config["writeIntervalMs"] / 1000, lambda: self._schedule(self.write(session)))

    async def drain(self, session=None):
        if session is not None:
            while self.writes.get(session):
                await asyncio.gather(*list(self.writes[session]), return_exceptions=True)
            return
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)

    async def close(self):
        self.closed = True
        for session in list(self.dirty):
            self._clean(session)
        await self.drain()


class SessionProjectionCachePlugin(Plugin):
    id = "session-projection-cache"
    inject = ["storageDomain", "sessionProjections", "sessions"]

    async def apply(self, ctx):
        for key in ("writeEveryEvents", "writeIntervalMs"):
            if type(self.config.get(key)) is not int or self.config[key] < 1:
                raise ValueError("session-projection-cache requires positive " + key)
        domain = await ctx.get("storageDomain").open(PROJECTION_CACHE_SPEC)
        cache = SessionProjectionCache(ctx, domain.table("sessions"), self.config)
        ctx.set_service("sessionProjectionCache", cache)
        ctx.on("session/event", cache.event)
        ctx.on("session/created", lambda session: cache._schedule(cache.write(session)))
        ctx.on("session/disposed", lambda session: cache._schedule(cache.write(session)))

        async def close():
            await cache.close()
            await domain.close()

        ctx.effect(lambda: close)
