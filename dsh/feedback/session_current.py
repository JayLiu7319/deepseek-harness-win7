"""Current Session feedback producer and public Remote, independent of telemetry."""
from dsh.cordis.plugin import Plugin
from dsh.cordis.text import trim_js
from dsh.identity.anonymous_user_id import get_or_create_anonymous_user_id
from dsh.typert.remote import Remote, TypertRemoteService

FEEDBACK_CATEGORIES = ('task-result', 'instruction-following', 'product-interaction',
                       'service-stability', 'resource-cost', 'security-privacy-permission', 'other')


def record_feedback(session, entry):
    text = trim_js(entry.get('text') or '')
    data = dict(text=text) if text else {}
    if 'category' in entry:
        data['category'] = entry['category']
    session.append('feedback/record', data)


def execute_feedback_command(invocation):
    raw = invocation.rawInput
    if not trim_js(raw):
        return dict(kind='error', text='Feedback text is required. Usage: /feedback <text>')
    session = invocation.agent.session
    record_feedback(session, dict(text=raw))
    return dict(kind='success', text='Feedback recorded for session {}\nAnonymous user: {}.'.format(session.id, get_or_create_anonymous_user_id()))


class CurrentSessionFeedback(TypertRemoteService):
    inject = ['sessions']

    def __init__(self, ctx, config=None):
        super().__init__(ctx, 'sessionFeedback')

    @Remote('record')
    async def record(self, request):
        session = self.ctx.get('sessions').get(request['sessionId'])
        if session is None:
            return dict(ok=False, error=dict(code='session-not-found', sessionId=request['sessionId']))
        record_feedback(session, request)
        return dict(ok=True, value=dict(recorded=True))


class CurrentCommandFeedback(Plugin):
    id = 'command-feedback'
    inject = ['commands']

    def apply(self, ctx):
        ctx.plugin(CurrentSessionFeedback)
        ctx.get('commands').register(dict(name='feedback', description='record feedback about this session',
            input=dict(hint='<text>'), recordInput=False, handler=execute_feedback_command))
