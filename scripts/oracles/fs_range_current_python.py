"""Actual regular-file byte windows against both current filesystem providers."""
import asyncio
import base64
import tempfile
from pathlib import Path
from dsh.core.abort import AbortController
from dsh.fs.fs_local import FsService


async def run(case):
    controller=AbortController()
    with tempfile.TemporaryDirectory(prefix='rc3-byte-range-') as folder:
        root=Path(folder);(root/'file.bin').write_bytes(base64.b64decode(case.get('data',''))*case.get('repeat',1))
        (root/'directory').mkdir()
        fs=FsService(folder)
        target=await fs.resolve(case.get('path','file.bin'))
        if case.get('aborted'):controller.abort()
        try:
            data=await fs.readByteRange(target,case['range'],controller.signal)
            return dict(data=base64.b64encode(data).decode('ascii'),bytes=len(data))
        except Exception as error:
            return dict(error=dict(message=str(error).replace(folder,'<root>'),code=getattr(error,'code',None)))


def execute(case):return asyncio.run(run(case))
