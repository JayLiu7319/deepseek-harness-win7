"""Actual asynchronous current image store; codec identity is separately scoped."""
import asyncio
import base64
import hashlib
import os
import tempfile
from pathlib import Path

from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.attachment.compression_current import CompressionLimiter
from dsh.core.abort import AbortController
from dsh.cordis.errors import ThrownValueError


def failure(error):
    result = dict(message=getattr(error, 'message', str(error)))
    if hasattr(error, 'code'):
        result['code'] = error.code
    if getattr(error, 'cause', None) is not None:
        result['cause'] = error.cause
    return result


async def run(case):
    async def outcome(awaitable):
        try:
            value = await awaitable
            return dict(value=value)
        except Exception as error:
            return dict(error=failure(error))
    if case['operation'] == 'limiter':
        limiter, order, active, peak = CompressionLimiter(2), [], 0, 0
        gate, entered = asyncio.Event(), asyncio.Event()
        async def work(index):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            order.append(index)
            if len(order) == 2:
                entered.set()
            try:
                await gate.wait()
                if index == 1:
                    raise ThrownValueError('binding failed')
                return index
            finally:
                active -= 1
        tasks = [asyncio.ensure_future(outcome(limiter.run(lambda index=index: work(index)))) for index in range(5)]
        await entered.wait()
        before = list(order)
        gate.set()
        values = await asyncio.gather(*tasks)
        return dict(before=before, order=order, peak=peak, values=values)
    with tempfile.TemporaryDirectory(prefix='rc3-img-') as directory:
        try:
            try:
                store = CurrentLocalAttachmentStore(config=dict(dshHome=directory, **case.get('config', {})))
            except Exception as error:
                return dict(error=failure(error))
            data = base64.b64decode(case['data'])
            ref = await store.saveImage(dict(data=data, mediaType='image/png'))
            policy = case.get('policy', dict(maxPixels=1000, maxBytes=10000))
            operation = case['operation']
            if operation == 'read':
                async def read():
                    result = await store.readImageRequest(ref, policy)
                    return {key: result[key] for key in ('attachment', 'mediaType', 'bytes', 'width', 'height', 'depth', 'space', 'hasAlpha')}, hashlib.sha256(result['data']).hexdigest()
                try:
                    result, digest = await read()
                    repeated, second = await read()
                    return dict(result=result, digest=digest, repeatEqual=result == repeated and digest == second)
                except Exception as error:
                    return dict(error=failure(error))
            started, entered, gates, signals = 0, asyncio.Queue(), [], []
            original = store.readImage
            async def blocked(ref, signal=None):
                nonlocal started
                index = started
                started += 1
                gate = asyncio.Event()
                gates.append(gate)
                signals.append(signal)
                entered.put_nowait(index)
                await gate.wait()
                signal.throwIfAborted()
                return await original(ref, signal)
            store.readImage = blocked
            first, second = AbortController(), AbortController()
            async def request(signal):
                result = await store.readImageRequest(ref, policy, signal)
                return dict(bytes=result['bytes'], width=result['width'], height=result['height'])
            one = asyncio.ensure_future(outcome(request(first.signal)))
            await entered.get()
            two = asyncio.ensure_future(outcome(request(second.signal)))
            await asyncio.sleep(0)
            first.abort('stop one' if case.get('nonError') else RuntimeError('stop one'))
            observed = await one
            if operation == 'shared':
                master_aborted = signals[0].aborted
                gates[0].set()
                other = await two
                return dict(started=started, first=observed, second=other, masterAborted=master_aborted)
            second.abort(RuntimeError('stop two'))
            other = await two
            replacement = asyncio.ensure_future(outcome(request(None)))
            await entered.get()
            gates[0].set()
            # Await old completion before asking a third waiter to join the new generation.
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            third = asyncio.ensure_future(outcome(request(None)))
            await asyncio.sleep(0)
            gates[1].set()
            return dict(first=observed, second=other, replacement=await replacement,
                        third=await third, started=started, oldAborted=signals[0].aborted)
        finally:
            for parent, _, files in os.walk(directory):
                for name in files:
                    os.chmod(os.path.join(parent, name), 0o600)


def execute(case):
    return asyncio.run(run(case))
