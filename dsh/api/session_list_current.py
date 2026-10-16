"""Zero-I/O list hints and bounded, authorized rc.3 Session message search."""
from dsh.api.session_list import list_metadata
from dsh.api.session_commands_current import error_text
from dsh.cordis.text import trim_js
from dsh.session.session_query import SessionQueryError
from dsh.typert.remote import RemoteError


def metadata_schema(value):
    if type(value.get('blank')) is not bool or (value.get('lastPromptAt') is not None and type(value['lastPromptAt']) not in (int, float)):
        raise ValueError('invalid Session list metadata')
    return dict(blank=value['blank'], lastPromptAt=value['lastPromptAt'])


def image_limits_schema(value):
    keys = ('maxImageBytes', 'maxImagesPerMessage', 'maxMessageImageBytes', 'maxImagePixels', 'maxImageDimension')
    if any(type(value.get(key)) not in (int, float) or value[key] <= 0 or not value[key] < float('inf') or int(value[key]) != value[key] for key in keys):
        raise ValueError('invalid image limits')
    if not isinstance(value.get('mediaTypes'), (list, tuple)) or any(not isinstance(item, str) for item in value['mediaTypes']):
        raise ValueError('invalid image media types')
    return dict({key: value[key] for key in keys}, mediaTypes=list(value['mediaTypes']))


def normalize_search_query(query):
    normalized = trim_js(query)
    if not normalized:
        raise RemoteError('gateway/bad-request', 'session search query must not be empty', {})
    if len(normalized.encode('utf-16-le', 'surrogatepass')) // 2 > 500:
        raise RemoteError('gateway/bad-request', 'session search query must contain at most 500 UTF-16 code units', {})
    if '\0' in normalized:
        raise RemoteError('gateway/bad-request', 'session search query must not contain NUL', {})
    return normalized


class CurrentSessionList:
    def __init__(self, ctx):
        self.ctx = ctx
        ctx.get('sessionProjections').register(dict(key='sessionListMetadata', stateVersion=1, stateSchema=metadata_schema,
            init=lambda *_: dict(blank=True, lastPromptAt=None), apply=list_metadata,
            wire=dict(viewSchema=metadata_schema, view=lambda value: value)))
        def images(child):
            def null_schema(value):
                if value is not None:
                    raise ValueError('image limits state must be null')
                return None
            ctx.get('sessionProjections').register(dict(key='imageLimits', stateVersion=1, stateSchema=null_schema,
                init=lambda *_: None, apply=lambda state, _: state,
                wire=dict(viewSchema=image_limits_schema, view=lambda _: child.get('attachments').imageLimits)))
        ctx.inject(['attachments'], images)

    def projections_for(self, header, session=None):
        try:
            if session is not None:
                block = self.ctx.get('sessionProjections').cachedSnapshot(session)
            else:
                cache = self.ctx.get('sessionProjectionCache')
                block = None if header.isSeeded or cache is None else (cache.cachedSnapshot(header, 0) or cache.cachedPredecessorTitle(header, 0))
            return dict(asOfSeq=block['asOfSeq'], values=block['values']) if block is not None and block['values'] else None
        except Exception as error:
            self.ctx.logger.warn('api-session.list: projection column for "{}" failed; serving the row without it: {}'.format(header.id, error_text(error)))
            return None

    def _summary(self, header, session=None):
        projections = self.projections_for(header, session)
        metadata = (projections or {}).get('values', {}).get('sessionListMetadata')
        agent = self.ctx.get('agents').get(header.id) if session is not None else None
        value = dict(sessionId=header.id, updatedAt=max(header.createdAt, metadata['lastPromptAt'] or 0 if metadata is not None else 0),
            running=agent is not None and agent.status == 'running', blank=metadata['blank'] if metadata is not None else session.seq == 0 if session is not None else False)
        for key, field in [('parentSessionId', header.parentSession), ('origin', header.origin), ('cwd', header.cwd), ('projections', projections)]:
            if field is not None:
                value[key] = field
        return value

    def summaryFor(self, session):
        return self._summary(session.header, session)

    async def list(self, signal=None):
        if signal is not None:
            signal.throwIfAborted()
        records = await self.ctx.get('sessionQuery').listSessions(signal)
        if signal is not None:
            signal.throwIfAborted()
        items, cold = [], []
        for record in records:
            header = record['header']
            live = self.ctx.get('sessions').get(header.id)
            if live is not None:
                items.append(self.summaryFor(live))
            elif header.cwd is not None:
                cold.append(header)
        items.extend(self._summary(header) for header in cold)
        return sorted(items, key=lambda value: -value['updatedAt'])

    async def search(self, query, signal):
        query = normalize_search_query(query)
        signal.throwIfAborted()
        provider = self.ctx.get('sessionQuery')
        if provider is None:
            raise RemoteError('gateway/internal', 'session search is unavailable: this deployment does not mount @deepseek-ai/dsh-session-query', {})
        try:
            visible = await provider.listSessions(signal)
            signal.throwIfAborted()
            visible_ids = {record['header'].id for record in visible if record['header'].cwd is not None}
            if not visible_ids:
                return dict(items=[], hasMore=False)
            authorized, accepted, cursors, cursor, calls, limit = [], set(), set(), None, 0, 20
            while len(authorized) <= 20:
                signal.throwIfAborted()
                if calls >= 100:
                    raise RuntimeError('session search provider exceeded the 100-call work budget')
                calls += 1
                try:
                    request = dict(query=query, eventFilters=[dict(kind='type', values=['user/message', 'assistant/message']), dict(kind='surface', values=['current'])], limit=limit)
                    if cursor is not None:
                        request['cursor'] = cursor
                    page = await provider.searchSessions(request, dict(signal=signal))
                    signal.throwIfAborted()
                except SessionQueryError as error:
                    signal.throwIfAborted()
                    if cursor is None and error.code == 'SESSION_QUERY_INVALID_LIMIT' and limit > 1:
                        limit = max(1, limit // 2)
                        continue
                    if cursor is not None and error.code == 'SESSION_QUERY_STALE_CURSOR':
                        authorized.clear(); accepted.clear(); cursors.clear(); cursor = None
                        continue
                    raise
                if len(page['items']) > limit:
                    raise RuntimeError('session search provider returned {} items; maximum is {}'.format(len(page['items']), limit))
                for hit in page['items']:
                    sid, match = hit['header'].id, hit['bestMatch']
                    if (len(authorized) > 20 or sid not in visible_ids or match['sessionId'] != sid or match['surface'] != 'current' or
                        match['type'] not in ('user/message', 'assistant/message') or sid in accepted):
                        continue
                    accepted.add(sid)
                    authorized.append(dict(sessionId=sid, snippet=match['snippet'][:240]))
                next_cursor = page.get('nextCursor')
                if next_cursor is not None:
                    if next_cursor in cursors:
                        raise RuntimeError('session search provider repeated a continuation cursor')
                    cursors.add(next_cursor)
                if len(authorized) > 20 or next_cursor is None:
                    break
                cursor = next_cursor
            return dict(items=authorized[:20], hasMore=len(authorized) > 20)
        except Exception as error:
            signal.throwIfAborted()
            if isinstance(error, SessionQueryError) and error.code == 'SESSION_QUERY_ABORTED':
                raise RemoteError('gateway/cancelled', 'session search was aborted', {}) from None
            raise RemoteError('gateway/internal', 'session search failed: ' + error_text(error), {}) from None
