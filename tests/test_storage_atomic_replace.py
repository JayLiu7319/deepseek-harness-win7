import asyncio
from pathlib import Path

import pytest

from dsh.storage import storage_json


@pytest.mark.parametrize('code', [5, 32, 33])
def test_windows_transient_replace_preserves_durable_temporary_file(tmp_path, monkeypatch, code):
    destination = tmp_path / 'record.json'
    destination.write_text('old', encoding='utf-8')
    replace = storage_json.os.replace
    attempts, waits = [], []

    def contested(source, target):
        attempts.append(Path(source).read_text(encoding='utf-8'))
        if len(attempts) < 3:
            error = PermissionError('destination temporarily held')
            error.winerror = code
            raise error
        replace(source, target)

    async def wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr(storage_json.os, 'replace', contested)
    monkeypatch.setattr(storage_json.asyncio, 'sleep', wait)
    asyncio.run(storage_json.write_atomic(str(destination), 'new'))
    assert attempts == ['new'] * 3
    assert waits == [0.01, 0.02]
    assert destination.read_text(encoding='utf-8') == 'new'
    assert list(tmp_path.glob('*.tmp')) == []


@pytest.mark.parametrize('code,expected_attempts', [(5, 6), (112, 1)])
def test_replace_failure_is_bounded_and_keeps_original_record(tmp_path, monkeypatch, code, expected_attempts):
    destination = tmp_path / 'record.json'
    destination.write_text('old', encoding='utf-8')
    attempts = []
    error = OSError('replacement failed')
    error.winerror = code

    def fail(source, target):
        attempts.append(source)
        raise error

    async def wait(seconds):
        pass

    monkeypatch.setattr(storage_json.os, 'replace', fail)
    monkeypatch.setattr(storage_json.asyncio, 'sleep', wait)
    with pytest.raises(OSError) as caught:
        asyncio.run(storage_json.write_atomic(str(destination), 'new'))
    assert caught.value is error
    assert len(attempts) == expected_attempts
    assert destination.read_text(encoding='utf-8') == 'old'
    assert list(tmp_path.glob('*.tmp')) == []
