"""Actual file publication, bounded I/O, cancellation and downstream admission."""
import asyncio
import json
import os
import threading
from pathlib import Path

import pytest

from dsh.attachment.error import AttachmentError
from dsh.attachment import immutable_current as publication
from dsh.attachment.files_current import read_file_stream_verbatim, save_file_stream_verbatim
from dsh.attachment.store_current import CurrentAttachmentStore, CurrentLocalAttachmentStore, is_attachment_error
from dsh.core.abort import AbortController
from scripts.oracles.attachment_files_current_python import execute

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / 'scripts/oracles/attachment_files_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_actual_original_file_contract(case):
    result = execute(case)
    assert result == case['expected']
    rows = result['results']
    if case['case'] in ('files-verbatim', 'files-stream', 'files-empty-encoded', 'files-concurrent', 'files-bounded-read'):
        assert rows[0]['outcome'] == 'value'  # A matching pair of failed actors is insufficient.
    if case['case'] == 'files-verbatim':
        assert rows[3]['value']['hex'] == '000102fafbfc'
        assert rows[2]['value'] == dict(sameObject=True, readOnly=True, staging=[])
    if case['case'] == 'files-prompt-admission':
        assert rows[0]['value']['images'] == []
        assert [part['type'] for part in rows[1]['value']['content']] == ['image', 'text', 'file', 'image']


@pytest.mark.asyncio
async def test_upload_is_pulled_only_after_previous_chunk_reaches_disk(tmp_path):
    root = str(tmp_path / 'attachments' / 'v1')
    async def chunks():
        for index in range(24):
            staged = list((Path(root) / 'tmp').iterdir())
            assert len(staged) == 1
            assert staged[0].stat().st_size == index * 65536
            yield b'x' * 65536
    ref = await save_file_stream_verbatim(root, dict(data=chunks(), name='large.bin'))
    assert ref['bytes'] == 24 * 65536
    count = 0
    async for chunk in read_file_stream_verbatim(root, ref):
        assert len(chunk) <= 65536
        count += len(chunk)
    assert count == ref['bytes']
    # The helper owns every link; make them removable on Python 3.8 / NTFS.
    for path in tmp_path.rglob('*'):
        if path.is_file():
            os.chmod(str(path), 0o600)


@pytest.mark.asyncio
async def test_task_cancellation_finishes_inflight_write_before_descriptor_cleanup(tmp_path, monkeypatch):
    root = str(tmp_path / 'attachments' / 'v1')
    started, release = threading.Event(), threading.Event()
    real_write = publication.write_chunk
    def blocking_write(handle, chunk):
        started.set()
        assert release.wait(5)
        real_write(handle, chunk)
    monkeypatch.setattr(publication, 'write_chunk', blocking_write)
    async def chunks():
        yield b'owned bytes'
    task = asyncio.create_task(save_file_stream_verbatim(root, dict(data=chunks())))
    try:
        await asyncio.wait_for(asyncio.get_running_loop().run_in_executor(None, started.wait), 3)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list((Path(root) / 'tmp').iterdir()) == []
    assert not (Path(root) / 'file-objects').exists()


@pytest.mark.asyncio
async def test_alias_failure_is_visible_and_published_object_remains_valid(tmp_path, monkeypatch):
    store = CurrentLocalAttachmentStore(config={'dshHome': str(tmp_path)})
    original_link = os.link
    def link(source, target):
        if 'files' in Path(target).parts:
            raise OSError('alias fault')
        original_link(source, target)
    monkeypatch.setattr(os, 'link', link)
    with pytest.raises(AttachmentError) as caught:
        await store.saveFile(dict(data=b'exact', name='file.txt'))
    assert caught.value.code == 'ATTACHMENT_WRITE_FAILED'
    assert str(caught.value.cause) == 'alias fault'
    assert list((Path(store.root) / 'tmp').iterdir()) == []
    objects = [path for path in (Path(store.root) / 'file-objects').rglob('*') if path.is_file()]
    assert len(objects) == 1 and objects[0].read_bytes() == b'exact'
    os.chmod(str(objects[0]), 0o600)


@pytest.mark.asyncio
async def test_base_read_cancellation_precedes_unsupported_provider():
    controller = AbortController()
    reason = RuntimeError('cancelled first')
    controller.abort(reason)
    with pytest.raises(RuntimeError) as caught:
        await CurrentAttachmentStore().readFileStream({}, controller.signal).__anext__()
    assert caught.value is reason


@pytest.mark.parametrize('code,expected', [('INVALID_FILE_BASE64', True), ('ATTACHMENT_FILES_UNSUPPORTED', True),
    ('ABORTED', False), ([], False), (None, False)])
def test_attachment_error_is_structural_with_known_string_codes(code, expected):
    error = RuntimeError('external installation')
    error.code = code
    assert is_attachment_error(error) is expected
    assert not is_attachment_error({'code': 'ATTACHMENT_CORRUPT'})
