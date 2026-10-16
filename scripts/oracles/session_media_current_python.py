"""Current media contribution through the real exact Fetch registry."""
import asyncio
from types import SimpleNamespace
from urllib.parse import urlencode

from dsh.api.session_media_current import CurrentSessionMediaReferences
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.fs.fs_local import FsError
from dsh.host.connection.current import CurrentHostConnection


async def run(case):
    ctx, calls, controller = Context(), [], AbortController()
    target = dict(targetKey='opaque', displayPath=case.get('displayPath', 'C:/remote/photo.png'))
    async def resolve(path, options):
        calls.append(dict(method='resolve', path=path, signal=options['signal'] is controller.signal))
        if case.get('error'):
            if case['error'] == 'unexpected':
                raise RuntimeError('unexpected provider failure')
            raise FsError('provider failure', case['error'])
        return target
    async def stat(received, signal):
        calls.append(dict(method='stat', sameTarget=received is target, signal=signal is controller.signal))
        return case.get('info', dict(type='file', size=4))
    async def read(received, signal, maximum):
        calls.append(dict(method='read', sameTarget=received is target, signal=signal is controller.signal, maxBytes=maximum))
        return bytearray.fromhex('000102ff')
    ctx.set_service('fs', SimpleNamespace(resolve=resolve, stat=stat, readBytes=read))
    ctx.set_service('attachments', SimpleNamespace(imageLimits=dict(maxImageBytes=case.get('limit', 4))))
    connection = CurrentHostConnection(ctx, [], SimpleNamespace(isAuthenticated=lambda _: True))
    try:
        fiber = await ctx.plugin(CurrentSessionMediaReferences)
        url = 'http://dsh.internal/api/file' + ('?' + urlencode(dict(path=case['path'])) if 'path' in case else '')
        try:
            result = await connection.createSharedFetchHandler('/api').fetch(dict(url=url, path='/api/file', method=case.get('method', 'GET'),
                headers=case.get('headers', {}), signal=controller.signal))
            body = result['body']
            observed = dict(status=result['status'], headers=result['headers'],
                            hex='' if body is None else (body.encode('utf-8') if isinstance(body, str) else body).hex())
        except Exception as error:
            observed = dict(error=str(error))
        await fiber.dispose()
        return dict(response=observed, calls=calls, withdrawn='/api/file' not in connection.fetch_routes)
    finally:
        await ctx.fiber.dispose()


def execute(case):
    return asyncio.run(run(case))
