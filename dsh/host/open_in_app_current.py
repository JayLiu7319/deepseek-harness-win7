"""Connection-guarded rc.3 application routes on the shared HTTP carrier."""
import asyncio
import json
import math
import os
import re
from urllib.parse import quote, urlsplit

from dsh.cordis.plugin import Plugin
from dsh.cordis.environment import launch_environment_of
from dsh.core.abort import AbortController
from dsh.host.connection.http_current import StreamingRequestBody
from dsh.host.open_in_app_resolver_current import (CATALOG, JS_SPACE, is_directory,
    launch_resolved, resolve_launch, resolve_open_in_app_apps)
from dsh.host.open_in_app_icons_current import extract_app_icon

APPS_ROUTE, ICON_PREFIX, OPEN_ROUTE = '/open-in-app/apps', '/open-in-app/icon', '/open-in-app/open'
MAX_BODY_BYTES = 64 * 1024


def resolve_config(config):
    result = {}
    for key in ('probeTimeoutMs', 'iconTimeoutMs', 'launchWatchMs'):
        value = config.get(key)
        if type(value) not in (int, float) or not 1 <= value <= 600000 or not math.isfinite(value) or int(value) != value:
            raise ValueError('open-in-app: %s must be an integer from 1 through 600000' % key)
        result[key] = int(value)
    return result


def icon_id(request):
    value = request.get('raw_url', request.get('url', request.get('path', '')))
    pathname = urlsplit(value.replace('\\', '/')).path
    # WHATWG URL removes literal/percent-encoded dot segments but retains all
    # other percent encodings. The id is never decoded into another app name.
    parts = []
    for part in pathname.split('/'):
        dot = re.sub('%2e', '.', part, flags=re.IGNORECASE)
        if dot == '..':
            if parts:
                parts.pop()
        elif dot != '.':
            parts.append(part)
    pathname = quote('/'.join(parts), safe="/%:@!$&'()*+,;=-._~[]|")
    identity = pathname[len(ICON_PREFIX):]
    return identity[1:] if identity.startswith('/') else identity


async def send(response, status, payload=None, headers=None, raw=False):
    response.write_status(status)
    if payload is not None and not raw:
        headers = dict({'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store'}, **(headers or {}))
        payload = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    for key, value in (headers or {}).items():
        response.write_header(key, value)
    if payload is not None:
        response.write_body(payload)
    await response.finish()


async def read_bounded_body(request):
    stream = StreamingRequestBody(request, AbortController()).__aiter__()
    chunks, size = [], 0
    async def drain():
        try:
            async for _ in stream:
                pass
        except Exception:
            pass
    try:
        async for chunk in stream:
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                return None, asyncio.ensure_future(drain())
            chunks.append(chunk)
        return b''.join(chunks).decode('utf-8', 'replace'), None
    except BaseException:
        await stream.aclose()
        raise


class CurrentOpenInApp(Plugin):
    id = '@deepseek-ai/dsh-host-open-in-app'
    name = 'open-in-app'
    inject = ['webServer', 'connection', 'subprocess']
    # Probe/launch facts mirror Source's internal test seam. They are never
    # user config, and the composition supplies the executable resolver.
    catalog_internals = None

    def apply(self, ctx):
        caps = resolve_config(self.config)
        environment = launch_environment_of(ctx)
        ssh = any(getattr(environment.get_from(key, ['process']), 'value', '') != '' for key in ('SSH_CONNECTION', 'SSH_TTY'))
        async def executable(name):
            try:
                return await ctx.get('subprocess').resolveExecutable(name)
            except Exception:
                return None
        def facts():
            return dict(dict(ssh=ssh, resolveExecutable=executable), **(self.catalog_internals or {}))
        resolutions, icons = None, {}
        async def availability():
            nonlocal resolutions
            if resolutions is None:
                resolutions = asyncio.ensure_future(resolve_open_in_app_apps(caps['probeTimeoutMs'], facts()))
            return await resolutions
        async def icon_of(app, resolved):
            if app['id'] not in icons:
                icons[app['id']] = asyncio.ensure_future(extract_app_icon(app, resolved, caps['iconTimeoutMs'], facts()))
            return await icons[app['id']]
        async def refresh(app):
            available = await availability()
            fresh = await resolve_launch(app, caps['probeTimeoutMs'], facts())
            icons.pop(app['id'], None)
            if fresh is None:
                available.pop(app['id'], None)
            else:
                available[app['id']] = fresh
            return fresh
        async def admitted(request, response, method):
            rejection = ctx.get('connection').requestRejection(request)
            if rejection is not None:
                await send(response, rejection)
                return False
            if request.get('method') != method:
                await send(response, 405, headers={'allow': method})
                return False
            return True
        async def apps(request, response):
            if await admitted(request, response, 'GET'):
                await send(response, 200, dict(apps=list(await availability())))
        async def icon(request, response):
            if not await admitted(request, response, 'GET'):
                return
            identity = icon_id(request)
            app = next((app for app in CATALOG if app['id'] == identity), None)
            resolved = (await availability()).get(identity) if app is not None else None
            value = await icon_of(app, resolved) if resolved is not None else None
            if value is None:
                await send(response, 404, dict(code='not-found', message='no icon for ' + identity))
            else:
                await send(response, 200, value['bytes'], {'content-type': value['contentType'], 'cache-control': 'public, max-age=3600'}, raw=True)
        async def open_app(request, response):
            if not await admitted(request, response, 'POST'):
                return
            essence = request.get('headers', {}).get('content-type', '').split(';', 1)[0].strip(JS_SPACE).lower()
            if essence != 'application/json':
                await send(response, 415, dict(code='unsupported-media-type', message='content-type must be application/json'))
                return
            drain = None
            try:
                try:
                    text, drain = await read_bounded_body(request)
                except Exception:
                    await send(response, 400, dict(code='bad-request', message='request body unreadable'))
                    return
                if text is None:
                    await send(response, 413, dict(code='payload-too-large', message='request body is too large'))
                    return
                try:
                    parsed = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                except ValueError:
                    parsed = None
                if not isinstance(parsed, dict) or not isinstance(parsed.get('app'), str) or not isinstance(parsed.get('path'), str):
                    await send(response, 400, dict(code='bad-request', message='request body must be JSON with string "app" and "path"'))
                    return
                app = next((app for app in CATALOG if app['id'] == parsed['app']), None)
                resolved = (await availability()).get(app['id']) if app is not None else None
                if resolved is None:
                    await send(response, 400, dict(code='bad-request', message='unknown or unavailable app: ' + parsed['app']))
                    return
                path = parsed['path']
                if not path or not os.path.isabs(path):
                    await send(response, 400, dict(code='bad-request', message='path must be an absolute directory path'))
                    return
                if not is_directory(path):
                    await send(response, 404, dict(code='not-found', message='directory does not exist: ' + path))
                    return
                outcome = await launch_resolved(resolved, path, caps['launchWatchMs'], facts())
                if outcome == 'missing':
                    fresh = await refresh(app)
                    outcome = 'failed' if fresh is None else await launch_resolved(fresh, path, caps['launchWatchMs'], facts())
                if outcome == 'launched':
                    await send(response, 200, dict(ok=True))
                else:
                    await send(response, 502, dict(code='launch-failed', message='failed to launch ' + app['id']))
            finally:
                if drain is not None:
                    drain.cancel()
                    await asyncio.gather(drain, return_exceptions=True)
        for kind, path, handler in [('exact', APPS_ROUTE, apps), ('prefix', ICON_PREFIX, icon), ('exact', OPEN_ROUTE, open_app)]:
            handler.defer_body = True
            ctx.effect(lambda kind=kind, path=path, handler=handler: ctx.get('webServer').register(kind, path, handler))
