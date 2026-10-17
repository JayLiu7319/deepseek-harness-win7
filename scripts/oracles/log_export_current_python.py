"""Invoke the current exporter over an observed persistence/attachment seam."""
import asyncio
import copy
from types import SimpleNamespace

from dsh.core.abort import NEVER_ABORTED
from dsh.session.log_export_current import serialize_session_log, read_session_log_text, session_log_zip_entries
from dsh.session.persistence import SessionPersistenceNotFoundError


def execute(test):
    async def run():
        trace = []
        class Persistence:
            async def open(self, sid, access, options):
                trace.append(['open', sid, access, bool(options.get('signal'))])
                if test.get('openError'):
                    if test['openError'] == 'missing':
                        raise SessionPersistenceNotFoundError(sid)
                    raise RuntimeError(test['openError'])
                if sid not in test['logs']:
                    raise SessionPersistenceNotFoundError(sid)
                record = copy.deepcopy(test['logs'][sid])
                async def read(start, end, options):
                    trace.append(['read', sid, start, bool(options.get('signal'))])
                    if test.get('readError'):
                        raise RuntimeError(test['readError'])
                    return dict(events=record['events'])
                async def close():
                    trace.append(['close', sid])
                    if test.get('closeError'):
                        raise RuntimeError(test['closeError'])
                return SimpleNamespace(header=record['header'], read=read, close=close)
        class Sessions:
            def get(self, sid):
                return sid if sid in test.get('live', []) else None
            async def flush(self, sid):
                trace.append(['flush', sid])
        class Query:
            async def traceSession(self, sid, options):
                trace.append(['trace', sid])
                return dict(descendants=test.get('descendants', []))
        class Attachments:
            async def readImage(self, ref, signal):
                trace.append(['image', ref['attachmentId']])
                return dict(data=bytes([1, 2, 3]))
            async def readFileStream(self, ref, signal):
                trace.append(['file', ref['attachmentId'], ref['name']])
                yield bytes([4, 5])
                yield bytes([6])
        services = dict(sessionPersistence=Persistence(), sessions=Sessions(), sessionQuery=Query(), attachments=Attachments())
        ctx = SimpleNamespace(get=services.get)
        try:
            op = test['operation']
            if op == 'serialize':
                log = test['logs']['root']
                value = serialize_session_log(log['header'], log['events'])
            elif op == 'read':
                value = await read_session_log_text(services['sessionPersistence'], test.get('id', 'root'),
                                                    NEVER_ABORTED if test.get('signal') else None)
            else:
                value = []
                root = serialize_session_log(test['logs']['root']['header'], test['logs']['root']['events'])
                async for row in session_log_zip_entries(ctx, root, 'root', test.get('includeDescendants', False)):
                    if 'chunks' in row:
                        row = dict(path=row['path'], chunks=[list(chunk) async for chunk in row['chunks']])
                    elif 'data' in row:
                        row = dict(path=row['path'], data=list(row['data']))
                    value.append(row)
            return dict(value=value, trace=trace)
        except Exception as error:
            return dict(error=str(error), trace=trace)
    return asyncio.run(run())
