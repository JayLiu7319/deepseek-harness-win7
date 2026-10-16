"""Authenticated current /api/file contribution over the execution-world FS."""
import json
import ntpath
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dsh.cordis.plugin import Plugin
from dsh.fs.fs_local import FsError
from dsh.host.connection.rpc_host import response

# Frozen from mime-types used by pinned rc.3, independent of Windows registry.
MIME_TYPES = json.loads((Path(__file__).resolve().parents[1] / 'resources/mime_types_current.json').read_text(encoding='utf-8'))
BASE_HEADERS = {'cache-control': 'private, no-store', 'x-content-type-options': 'nosniff',
                'content-security-policy': "sandbox; default-src 'none'"}
ERROR_STATUSES = dict(FS_NOT_FOUND=404, FS_NOT_REGULAR_FILE=403, FS_PERMISSION_DENIED=403,
                      FS_SANDBOX_DENIED=403, FS_TOO_LARGE=413, FS_ABORTED=499)


def field(value, name):
    return value.get(name) if isinstance(value, dict) else getattr(value, name, None)


def media_type(path):
    extension = ntpath.splitext(path)[1][1:].lower()
    return MIME_TYPES.get(extension, 'application/octet-stream')


async def serve_file(request, fs, max_bytes):
    head = request['method'] == 'HEAD'
    def fail(status, text):
        headers = dict(BASE_HEADERS)
        if not head:
            headers['content-type'] = 'text/plain;charset=UTF-8'
        return response(status, None if head else text, headers)
    path = parse_qs(urlsplit(request['url']).query, keep_blank_values=True).get('path', [None])[0]
    if path is None or path == '':
        return fail(400, 'missing path')
    if '\0' in path or not os.path.isabs(path):
        return fail(400, 'absolute path required')
    signal = request.get('signal')
    try:
        target = await fs.resolve(path, dict(signal=signal))
        headers = dict(BASE_HEADERS, **{'content-type': media_type(field(target, 'displayPath'))})
        if head:
            info = await fs.stat(target, signal)
            if info is None:
                return fail(404, 'not found')
            if field(info, 'type') != 'file':
                return fail(403, 'not a regular file')
            size = field(info, 'size')
            if size is not None:
                if size > max_bytes:
                    return fail(413, 'file exceeds byte limit')
                headers['content-length'] = str(size)
            return response(200, None, headers)
        data = bytes(await fs.readBytes(target, signal, max_bytes))
        headers['content-length'] = str(len(data))
        return response(200, data, headers)
    except FsError as error:
        return fail(ERROR_STATUSES.get(error.code, 500), error.code)


class CurrentSessionMediaReferences(Plugin):
    inject = ['connection', 'fs', 'attachments']

    def apply(self, ctx):
        max_bytes = ctx.get('attachments').imageLimits['maxImageBytes']
        ctx.effect(lambda: ctx.get('connection').fetch.register(dict(path='/api/file', methods=['GET', 'HEAD'],
            requestBody='buffered', fetch=lambda request: serve_file(request, ctx.get('fs'), max_bytes))),
            'session-controller: /api/file')
