"""Qualify product-owned compatibility against actual archived alpha SQLite files.

This is an rc.1 product compatibility check; its historical input is never
presented as an rc.1 Source persistence provider.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = 'migration/history/2026-10-14-alpha1/sqlite-reader-fixtures.zip'
MODULES = ['dsh/session/sqlite_legacy_reader.py', 'dsh/session/sqlite_store.py',
           'dsh/session/sqlite_database.py', 'dsh/session/sqlite_schema.py',
           'dsh/session/sqlite_logical.py', 'dsh/session/persistence_sqlite_canonical.py',
           'dsh/session/persistence_jsonl_canonical.py', 'dsh/session/lineage_storage.py',
           'dsh/boot/plugin_registry.py', 'dsh/llm/plugin_package_inventory.py',
           'dsh/session/legacy-sqlite-reader/package.json']


def hashes(root):
    paths = MODULES + [p.relative_to(root).as_posix() for directory in
        ('dsh/session/bin', 'dsh/session/resources/sql') for p in (root / directory).rglob('*') if p.is_file()]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(paths)}


async def observe(root, workspace):
    sys.path.insert(0, str(root))
    from dsh.session.sqlite_legacy_reader import LegacySqliteSessionReader
    from dsh.session.persistence_jsonl_canonical import JsonlSessionPersistence
    from dsh.boot.plugin_registry import HARNESS_PLUGIN_CLASSES
    # The writable alpha provider and report tool no longer mount under upstream names.
    assert '@deepseek-ai/dsh-session-persistence-sqlite' not in HARNESS_PLUGIN_CLASSES
    assert '@deepseek-ai/dsh-tool-subagent-report' not in HARNESS_PLUGIN_CLASSES
    fixture = ROOT / FIXTURE
    manifest = json.loads(fixture.with_suffix('.json').read_text(encoding='utf-8'))
    assert manifest['source_commit'] == 'cd5ef8148158c3a752a658978873241fdf8e2bbc'
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == manifest['archive_sha256']
    rows = []
    with zipfile.ZipFile(fixture) as archive:
        for item, session_id, count in zip(manifest['files'], ['store-session', 'cold-packed'], [2054, 104]):
            raw = archive.read(item['path'])
            assert hashlib.sha256(raw).hexdigest() == item['sha256']
            database = workspace / item['path']
            database.write_bytes(raw)
            reader = LegacySqliteSessionReader(str(database))
            try:
                inspection = await reader.inspect(session_id)
                assert len(inspection.events) == count and inspection.inheritedEventCount == 0
                assert inspection.meta.isSeeded is False
                try:
                    reader._backend.store.database.exec('DELETE FROM sessions')
                except Exception as error:
                    assert 'readonly' in str(error)
                else:
                    raise AssertionError('historical database accepted a write')
                for compression in ('none', 'zstd'):
                    output = workspace / (session_id + '-' + compression)
                    await reader.export(session_id, str(output), compression)
                    try:
                        await reader.export(session_id, str(output), compression)
                    except ValueError:
                        pass
                    else:
                        raise AssertionError('export replaced an existing conversation')
                    target = JsonlSessionPersistence(str(output), compression=compression)
                    try:
                        cold = await target.inspect(session_id)
                        assert cold.meta == inspection.meta and cold.events == inspection.events
                        prepared = await target.prepare(session_id)
                        try:
                            assert prepared.session.inheritedEventCount == 0
                            assert prepared.session.firstLiveSeq >= count
                            next_seq = prepared.session.seq
                            recovery = prepared.session.snapshotEvents(count)
                        finally:
                            prepared.dispose()
                        if recovery:
                            await target.append(session_id, recovery)
                        await target.append(session_id, [dict(seq=next_seq, time=1, type='turn/start', data=dict(turn=2)),
                            dict(seq=next_seq + 1, time=2, type='turn/end', data=dict(turn=2, reason=dict(kind='completed')))])
                        assert (await target.inspect(session_id)).events[-1]['seq'] == next_seq + 1
                    finally:
                        await target.prepared().drain()
                        await target.close()
                    rows.append(dict(sessionId=session_id, compression=compression, count=count,
                                     readonly=True, duplicateRefused=True, coldResume=True))
            finally:
                await reader.close()
            assert database.read_bytes() == raw
    return dict(status='passed', root=str(root), python=list(sys.version_info[:3]), modules=hashes(root),
                fixtureSha256=manifest['archive_sha256'], historicalSource=manifest['source_commit'], rows=rows)


def validate_runtime(report, root, expected_modules=None):
    root = Path(root).resolve()
    fixture = ROOT / FIXTURE
    expected = [dict(sessionId=sid, compression=compression, count=count, readonly=True,
                     duplicateRefused=True, coldResume=True)
                for sid, count in [('store-session', 2054), ('cold-packed', 104)]
                for compression in ('none', 'zstd')]
    if (not isinstance(report, dict) or report.get('status') != 'passed' or report.get('root') != str(root)
            or report.get('python') != [3, 8, 10] or report.get('rows') != expected
            or report.get('fixtureSha256') != hashlib.sha256(fixture.read_bytes()).hexdigest()
            or report.get('historicalSource') != 'cd5ef8148158c3a752a658978873241fdf8e2bbc'
            or report.get('modules') != (hashes(root) if expected_modules is None else expected_modules)):
        raise ValueError('legacy reader qualification is incomplete or belongs to another candidate')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--environment', type=Path)
    parser.add_argument('--runtime', action='store_true')
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.runtime:
        with tempfile.TemporaryDirectory(prefix='dsh-legacy-') as private:
            report = asyncio.run(observe(args.root.resolve(), Path(private)))
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    else:
        environment = json.loads(args.environment.read_text(encoding='utf-8')) if args.environment else os.environ.copy()
        result = subprocess.run([args.python, '-I', str(Path(__file__).resolve()), '--runtime', '--root', str(args.root),
                                 '--output', str(args.output.resolve())], env=environment, capture_output=True, timeout=90)
        args.output.with_suffix('.log').write_bytes(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError('legacy session reader failed; see ' + str(args.output.with_suffix('.log')))
        validate_runtime(json.loads(args.output.read_text(encoding='utf-8')), args.root)


if __name__ == '__main__':
    main()
