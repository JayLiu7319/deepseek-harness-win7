"""Existing home upgrades through the actual Desktop/workspace composition."""
import json
from pathlib import Path

import pytest

from dsh.host.desktop.runtime import run_desktop_host
from dsh.core.abort import AbortController
from dsh.host.desktop.session_compatibility import preserve_default_session_encoding
from dsh.session.jsonl_current import generationLogPath
from dsh.session.jsonl_zstd import compress_frame


def history(home, compression, version=0, identity='old-session'):
    # No cwd is represented by UNDEFINED, rather than a JSON null.
    from dsh.core.session.json import UNDEFINED
    path = Path(generationLogPath(str(home / 'sessions'), UNDEFINED, identity, version, compression))
    path.parent.mkdir(parents=True, exist_ok=True)
    header = dict(type='session', version=version, id=identity, createdAt=1, delegationDepth=0)
    if version >= 2:
        header['isSeeded'] = False
    data = (json.dumps(header) + '\n').encode('utf-8')
    path.write_bytes(compress_frame(data) if compression == 'zstd' else data)
    return path


@pytest.mark.asyncio
@pytest.mark.parametrize('compression', ['none', 'zstd'])
async def test_existing_home_boots_and_cold_opens_without_rewriting_history(tmp_path, monkeypatch, compression):
    home = tmp_path / 'home'
    monkeypatch.setenv('DSH_HOME', str(home))
    monkeypatch.setenv('DSH_TELEMETRY_DISABLED', '1')
    old = history(home, compression)
    future = history(home, compression, 4, 'future-session')
    original = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (old, future)}
    for _ in range(2):
        runtime = await run_desktop_host(tmp_path / 'profile')
        try:
            store = runtime.ctx.get('sessionPersistence')
            assert store.compression == compression
            assert [item['header']['id'] for item in await store.list()] == ['old-session']
            assert runtime.ctx.get('workspaceRegistry') is not None
            assert (await runtime.fetch(dict(url='dsh-app://app/index.html', method='GET', headers={}, signal=AbortController().signal)))['status'] == 200
        finally:
            await runtime.close()
    assert {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in (old, future)} == original
    assert not list(home.rglob('session.v3*'))


@pytest.mark.asyncio
@pytest.mark.parametrize('explicit', [False, True])
async def test_mixed_or_explicit_conflict_stays_an_error_and_releases_profile(tmp_path, monkeypatch, explicit):
    home = tmp_path / 'home'
    monkeypatch.setenv('DSH_HOME', str(home))
    monkeypatch.setenv('DSH_TELEMETRY_DISABLED', '1')
    old = history(home, 'none')
    if not explicit:
        history(home, 'zstd', 3, 'compressed-session')
    patches = [dict(id='session-persistence-jsonl', config=dict(root=str(home / 'sessions'), compression='zstd'))] if explicit else []
    with pytest.raises(Exception, match='configured for compression'):
        await run_desktop_host(tmp_path / 'profile', patches=patches)
    # Correcting the profile works after the failed boot; no process lease leaked.
    if not explicit:
        return
    runtime = await run_desktop_host(tmp_path / 'profile')
    await runtime.close()
    assert old.exists()


def test_custom_root_and_explicit_policy_are_not_guessed(tmp_path, monkeypatch):
    monkeypatch.setenv('DSH_HOME', str(tmp_path))
    history(tmp_path, 'none')
    base = dict(id='session-persistence-jsonl', name='@deepseek-ai/dsh-session-persistence-jsonl')
    for config in (dict(root=str(tmp_path / 'sessions')),
                   dict(root={'__jsExpr': "dshHomePath('sessions')"}, compression='zstd')):
        patches = [dict(insert=[dict(base, config=config)])]
        assert preserve_default_session_encoding(patches) == patches


@pytest.mark.asyncio
async def test_empty_home_still_defaults_to_zstd(tmp_path, monkeypatch):
    monkeypatch.setenv('DSH_HOME', str(tmp_path / 'home'))
    monkeypatch.setenv('DSH_TELEMETRY_DISABLED', '1')
    runtime = await run_desktop_host(tmp_path / 'profile')
    try:
        assert runtime.ctx.get('sessionPersistence').compression == 'zstd'
    finally:
        await runtime.close()
