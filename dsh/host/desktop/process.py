"""Python 3.8 Windows pipe adapter: stdin/stdout v3 bytes, stderr lifecycle."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

from dsh.core.abort import AbortController
from dsh.host.desktop.runtime import run_desktop_host
from dsh.host.desktop.wire import (CHUNK_BYTES, FrameDecoder, encode_start,
    encode_data, encode_end, encode_error)

CONTROL_PREFIX = 'DSH_DESKTOP_CONTROL '


class RequestBody:
    def __init__(self):
        self.queue, self.ended = asyncio.Queue(maxsize=16), False

    def feed(self, value):
        if self.ended:
            raise ValueError('dsh desktop: request body already ended')
        self.queue.put_nowait(value)
        if value is None:
            self.ended = True

    async def __aiter__(self):
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item


async def serve(profile_dir, output):
    runtime, requests, tasks = None, {}, set()
    lock = asyncio.Lock()
    loop = asyncio.get_running_loop()
    def control(value):
        sys.stderr.write(CONTROL_PREFIX + json.dumps(value, ensure_ascii=True) + '\n')
        sys.stderr.flush()
    def finished(task):
        tasks.discard(task)
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                control(dict(type='fatal', message=str(error)))
    def write_bytes(data):
        output.write(data)
        output.flush()
    async def write(data):
        async with lock:
            await loop.run_in_executor(None, write_bytes, data)
    async def dispatch(identity, state, request):
        controller = state['abort']
        try:
            response = await runtime.fetch(request)
            body = response.get('body')
            headers = response.get('headers', {})
            pairs = list(headers.items()) if isinstance(headers, dict) else headers
            await write(encode_start(identity, dict(status=response['status'], headers=[list(pair) for pair in pairs], hasBody=body is not None)))
            if isinstance(body, str):
                body = body.encode('utf-8')
            if isinstance(body, (bytes, bytearray)):
                for offset in range(0, len(body), CHUNK_BYTES):
                    controller.signal.throwIfAborted()
                    await write(encode_data(identity, body[offset:offset + CHUNK_BYTES]))
            elif body is not None:
                try:
                    async for chunk in body:
                        if isinstance(chunk, str):
                            chunk = chunk.encode('utf-8')
                        for offset in range(0, len(chunk), CHUNK_BYTES):
                            controller.signal.throwIfAborted()
                            await write(encode_data(identity, chunk[offset:offset + CHUNK_BYTES]))
                finally:
                    if hasattr(body, 'aclose'):
                        await body.aclose()
            controller.signal.throwIfAborted()
            await write(encode_end(identity))
        except asyncio.CancelledError:
            controller.abort('desktop stream cancelled')
            raise
        except Exception as error:
            if not controller.signal.aborted:
                await write(encode_error(identity, str(error)))
        finally:
            state['finished'] = True
            if state['body'] is None or state['body'].ended:
                requests.pop(identity, None)
    try:
        runtime = await run_desktop_host(profile_dir)
        from dsh import __version__
        control(dict(type='ready', protocolVersion=3, dshVersion=__version__))
        decoder = FrameDecoder()
        while True:
            chunk = await loop.run_in_executor(None, os.read, sys.stdin.fileno(), CHUNK_BYTES)
            if not chunk:
                decoder.finish()
                break
            for frame in decoder.push(chunk):
                identity, kind = frame['streamId'], frame['type']
                if kind == 'start':
                    if identity in requests:
                        raise ValueError('dsh desktop: duplicate active stream id')
                    if len(requests) >= 128:
                        raise ValueError('dsh desktop: too many active requests')
                    abort, body = AbortController(), RequestBody() if frame['hasBody'] else None
                    state = dict(abort=abort, body=body, finished=False)
                    requests[identity] = state
                    task = asyncio.ensure_future(dispatch(identity, state, dict(url=frame['url'], method=frame['method'],
                        headers={key.lower(): value for key, value in frame['headers']}, body=body, signal=abort.signal)))
                    state['task'] = task
                    tasks.add(task)
                    task.add_done_callback(finished)
                elif kind == 'cancel':
                    state = requests.pop(identity, None)
                    if state is not None:
                        state['abort'].abort('desktop caller cancelled')
                        state['task'].cancel()
                else:
                    state = requests.get(identity)
                    if state is None:
                        # A completed no-body request may already be retired.
                        if kind == 'end':
                            continue
                        raise ValueError('dsh desktop: data for unknown stream')
                    body = state['body']
                    if body is None:
                        if kind == 'data':
                            raise ValueError('dsh desktop: unexpected body data')
                    elif state['finished']:
                        if kind == 'end':
                            requests.pop(identity, None)
                    else:
                        try:
                            body.feed(frame['data'] if kind == 'data' else None)
                        except asyncio.QueueFull:
                            # Reject this stream rather than retaining an
                            # unbounded body for a route that does not consume it.
                            state['abort'].abort('desktop request body buffer exceeded')
                            state['task'].cancel()
                            await write(encode_error(identity, 'desktop request body buffer exceeded'))
                    if kind == 'end' and state['finished']:
                        requests.pop(identity, None)
    except BaseException as error:
        control(dict(type='fatal', message=str(error)))
        raise
    finally:
        for state in requests.values():
            state['abort'].abort('desktop host shutting down')
            state['task'].cancel()
        await asyncio.gather(*list(tasks), return_exceptions=True)
        if runtime is not None:
            await runtime.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile-dir', type=Path, required=True)
    parser.add_argument('--home', type=Path, required=True)
    options = parser.parse_args()
    os.environ['DSH_HOME'] = str(options.home.resolve())
    binary = sys.stdout.buffer
    # All plugin diagnostics belong to stderr. Only framed bytes use stdout.
    sys.stdout = sys.stderr
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    asyncio.run(serve(str(options.profile_dir.resolve()), binary))


if __name__ == '__main__':
    main()
