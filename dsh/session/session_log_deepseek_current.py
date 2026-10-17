"""Generation-scoped, lossless DeepSeek Session-log request contribution."""
import weakref

from dsh.cordis.plugin import Plugin
from dsh.cordis.utils import js_to_string
from dsh.core.session.current import safe
from dsh.core.session.current_vocabulary import KNOWN_SESSION_EVENT_TYPES
from dsh.core.session.types import SessionSeq
from dsh.core.session.json import UNDEFINED


ACCEPTED_EVENT_TYPE = 'session-log-deepseek/delivery-accepted'
_FOLDS = weakref.WeakKeyDictionary()


def accepted_through(session):
    previous = _FOLDS.get(session, dict(scannedEvents=0, throughSeq=-1))
    through = previous['throughSeq']
    length = session.seq
    for index in range(int(previous['scannedEvents']), int(length)):
        event = session.eventAt(index)
        if event is UNDEFINED:
            raise ValueError('session-log-deepseek: missing event %s below captured length %s' % (index, js_to_string(length)))
        if event['type'] != ACCEPTED_EVENT_TYPE:
            continue
        data, seq = event['data'], event['seq']
        version = data.get('sessionFormatVersion')
        version = 0 if version is None else version
        if not safe(version, True, True):
            raise ValueError('session-log-deepseek: malformed acceptance format version at seq ' + js_to_string(seq))
        if version != session.header.version:
            continue
        try:
            accepted = SessionSeq(data.get('throughSeq'))
        except (TypeError, ValueError):
            raise ValueError('session-log-deepseek: malformed acceptance watermark at seq ' + js_to_string(seq)) from None
        if not isinstance(data.get('sessionId'), str) or not data['sessionId'] or accepted >= seq:
            raise ValueError('session-log-deepseek: malformed acceptance watermark at seq ' + js_to_string(seq))
        if data['sessionId'] == session.id:
            through = max(through, accepted)
    _FOLDS[session] = dict(scannedEvents=length, throughSeq=through)
    return through


acceptedThrough = accepted_through


def wire_header(session):
    header = session.header
    result = dict(version=header.version, id=str(header.id), createdAt=header.createdAt)
    for key in ('cwd', 'parentSession', 'origin', 'delegationDepth', 'agentPreset'):
        value = getattr(header, key)
        if value is not None:
            result[key] = value
    if header.isSeeded:
        result['seedLength'] = session.inheritedEventCount
    return result


def wire_event(event):
    kind = event['type']
    result = {key: event[key] for key in ('type', 'seq', 'time', 'data')}
    if 'ignorable' in event:
        result['ignorable'] = event['ignorable']
    if kind in ('system/message', 'user/message', 'assistant/message', 'tool/result'):
        op = event['surfaceOp']
        result['surfaceOp'] = op if op == 'append' else {key: op[key] for key in ('op', 'startSeq', 'endSeq')}
        if kind != 'assistant/message' and 'sourceEventSeqs' in event:
            result['sourceEventSeqs'] = list(event['sourceEventSeqs'])
    elif kind not in KNOWN_SESSION_EVENT_TYPES and event.get('ignorable') is True:
        for key in ('surfaceOp', 'sourceEventSeqs'):
            if key in event:
                result[key] = event[key]
    return result


class CurrentSessionLogDeepSeekPlugin(Plugin):
    id = 'session-log-deepseek'
    inject = ['deepseekLlmApiExtensions', 'sessions']

    def apply(self, ctx):
        if self.config.get('enabled') is not True:
            return
        def prepare(request):
            identity = request.get('sessionId')
            session = ctx.get('sessions').get(identity) if identity is not None else None
            if session is None:
                return None
            after = accepted_through(session)
            events = session.snapshotEvents()
            if not events:
                return None
            through = events[-1]['seq']
            value = dict(version=1, sessionFormatVersion=session.header.version, session=wire_header(session),
                         afterSeq=after, throughSeq=through, events=[wire_event(e) for e in session.snapshotEvents(after + 1)])
            def accept():
                session.append(ACCEPTED_EVENT_TYPE, dict(sessionId=session.id,
                    sessionFormatVersion=session.header.version, throughSeq=through))
            return dict(value=value, accept=accept)
        ctx.get('deepseekLlmApiExtensions').register('dsh_session_log', dict(prepare=prepare))
