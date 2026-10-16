"""Actual Source byte windows plus bounded sparse-file reads and cancellation."""
import asyncio
import json
from pathlib import Path

import pytest

from dsh.core.abort import AbortController
from dsh.fs import fs_local
from dsh.fs.fs_local import FsError,FsService,READ_CHUNK_BYTES
from scripts.oracles.fs_range_current_python import execute
from scripts.session_format_oracle import json_equal

CASES=json.loads((Path(__file__).resolve().parents[1]/'scripts/oracles/fs_range_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case',CASES,ids=lambda case:case['case'])
def test_actual_source_byte_windows(case):
    assert json_equal(execute(case),case['expected'])


@pytest.mark.asyncio
async def test_sparse_file_window_seeks_and_never_reads_prefix(tmp_path,monkeypatch,request):
    path=tmp_path/'sparse.bin';offset=256*1024*1024
    with path.open('wb') as handle:
        handle.seek(offset);handle.write(b'\x00\xfftarget')
    request.addfinalizer(path.unlink)
    opened,reads=[],[]
    original=fs_local._open_binary_read
    class Observed:
        def __init__(self,path):self.handle=original(path)
        def __enter__(self):opened.append(True);return self
        def __exit__(self,*_):self.handle.close()
        def seek(self,position):assert position==offset;return self.handle.seek(position)
        def read(self,size):reads.append(size);return self.handle.read(size)
    monkeypatch.setattr(fs_local,'_open_binary_read',Observed)
    fs=FsService(str(tmp_path));target=await fs.resolve(str(path))
    assert await fs.readByteRange(target,dict(offset=offset,length=8))==b'\x00\xfftarget'
    assert opened==[True] and reads==[8]


@pytest.mark.asyncio
async def test_abort_between_chunks_closes_descriptor(tmp_path,monkeypatch):
    path=tmp_path/'large.bin';path.write_bytes(b'X'*(READ_CHUNK_BYTES+20))
    controller,opened=AbortController(),[]
    original=fs_local._open_binary_read
    class Observed:
        def __init__(self,path):self.handle=original(path);opened.append(self.handle)
        def __enter__(self):return self
        def __exit__(self,*_):self.handle.close()
        def seek(self,position):return self.handle.seek(position)
        def read(self,size):
            assert size<=READ_CHUNK_BYTES
            value=self.handle.read(size);controller.abort();return value
    monkeypatch.setattr(fs_local,'_open_binary_read',Observed)
    fs=FsService(str(tmp_path));target=await fs.resolve(str(path))
    with pytest.raises(FsError) as raised:
        await fs.readByteRange(target,dict(offset=0,length=READ_CHUNK_BYTES+20),controller.signal)
    assert raised.value.code=='FS_ABORTED' and all(handle.closed for handle in opened)
