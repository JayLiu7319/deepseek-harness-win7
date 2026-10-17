import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
import tempfile


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    root = options.root.resolve()
    sys.path.insert(0, str(root))
    from dsh.cordis.context import Context
    from dsh.core.session.current_session import CurrentSessionPlugin
    from dsh.core.abort import AbortController
    from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistencePlugin
    rows = []
    for name in ('jsonl-none/queued', 'jsonl-zstd/queued'):
        with tempfile.TemporaryDirectory(prefix='dsh-read-order-') as directory:
            ctx = Context()
            row = dict(name=name)
            controller = AbortController()
            reason = RuntimeError('controlled read retired')
            entered, released = asyncio.Event(), asyncio.Event()
            try:
                await ctx.plugin(CurrentSessionPlugin)
                await ctx.plugin(CurrentJsonlSessionPersistencePlugin, dict(root=directory, compression='zstd' if name.startswith('jsonl-zstd') else 'none'))
                provider = ctx.get('sessionPersistence')
                handle = await provider.create(dict(id='s',version=3,createdAt=1,isSeeded=False))
                await handle.append([dict(type='session/end-seed',seq=0,time=1,data={})])
                original = provider.readStoredLog
                calls = []
                async def held(*args):
                    first = not calls
                    calls.append(dict(signalForwarded=args[-1] is controller.signal))
                    if not first:
                        controller.abort(reason)
                    result = await original(*args)
                    if first:
                        entered.set()
                        await released.wait()
                    return result
                provider.readStoredLog = held
                async def settle(reading):
                    try:
                        return dict(value=await reading)
                    except Exception as error:
                        return dict(error=dict(name='TypeError' if isinstance(error,TypeError) else 'Error',message=str(error)),reasonIdentity=error is reason)
                first = asyncio.create_task(settle(handle.read()))
                await asyncio.wait_for(entered.wait(),5)
                second = asyncio.create_task(settle(handle.read(0,options=dict(signal=controller.signal))))
                try:
                    await asyncio.wait_for(asyncio.shield(second),1)
                    row['settledBeforeRelease'] = True
                except asyncio.TimeoutError:
                    row['settledBeforeRelease'] = False
                row['callsBeforeRelease'] = len(calls)
                released.set()
                row['first'] = await first
                row.update(await second)
                row.update(calls=calls,aborted=controller.signal.aborted)
                provider.readStoredLog = original
            finally:
                released.set()
                await ctx.fiber.dispose()
            rows.append(row)
    modules = {}
    for name, module in sorted(sys.modules.items()):
        path = getattr(module, '__file__', None)
        if path and (name == 'dsh' or name.startswith('dsh.')):
            selected = Path(path).resolve()
            modules[selected.relative_to(root).as_posix()] = hashlib.sha256(selected.read_bytes()).hexdigest()
    with options.output.open('x', encoding='utf-8') as stream:
        json.dump(dict(root=str(root), python=sys.version, executable=sys.executable, modules=modules, rows=rows), stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    asyncio.run(main())
