"""Opt-in, read-only migration of schema-19 alpha Session databases.

This product compatibility service is not an rc.1 upstream persistence backend.
Exports refuse duplicate target identities and leave the source database intact.
"""
from dsh.cordis.plugin import Plugin
from dsh.cordis.schema import Schema
from dsh.session.persistence_sqlite_canonical import SqliteSessionPersistence
from dsh.session.sqlite_store import SqliteStore
from dsh.session.persistence_jsonl_canonical import JsonlSessionPersistence


class LegacySqliteSessionReader:
    def __init__(self, path):
        self._backend = SqliteSessionPersistence(path)
        self._backend.store = SqliteStore(path, read_only=True)

    async def list(self, signal=None):
        return await self._backend.list(signal)

    async def inspect(self, session_id, signal=None):
        return await self._backend.inspect(session_id, signal)

    async def export(self, session_id, output_root, compression='zstd'):
        inspection = await self.inspect(session_id)
        target = JsonlSessionPersistence(output_root, compression=compression)
        try:
            await target.create(inspection.meta, inspection.inheritedEventCount)
            if inspection.events:
                await target.append(session_id, inspection.events)
            else:
                await target._create(inspection.meta)
            return target.locate(inspection.meta)
        finally:
            await target.prepared().drain()
            await target.close()

    async def close(self):
        await self._backend.prepared().drain()
        await self._backend.close()


class LegacySqliteSessionReaderPlugin(Plugin):
    id = 'legacy-session-sqlite-reader'
    name = '@deepseek-ai/dsh-win7-session-sqlite-reader'
    Config = Schema.object({'path': Schema.string().required()})

    def apply(self, ctx):
        reader = LegacySqliteSessionReader(self.config['path'])
        ctx.set_service('legacySessionReader', reader)
        ctx.disposable(reader.close, label='legacy session reader')
