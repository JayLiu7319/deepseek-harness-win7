"""rc.3 prompt, queue and attachment commands over explicit Agent ownership."""
import base64

from dsh.attachment.error import AttachmentError
from dsh.cordis.text import trim_js
from dsh.llm.message import create_user_message, freeze_message
from dsh.llm.assistant_stream import assistantStreamChunks
from dsh.session.session_query import SessionQueryError
from dsh.typert.remote import RemoteError, remote_error_of
from dsh.util_time import canonical_client_time_zone


def has_prompt_content(content):
    return any(part['type'] != 'text' or trim_js(part['text']) for part in content)


def has_subagent_owner(ctx, session, agent=None):
    if session.header.origin == 'subagent':
        return True
    parent_id = session.header.parentSession
    parent = ctx.get('agents').get(parent_id) if parent_id is not None else None
    return parent is not None and agent is not None and ctx.get('agents').isOwnedBy(agent.id, parent)


def ownership_error(session_id):
    return RemoteError('session/agent-busy', 'session "{}" is owned by subagent routing'.format(session_id),
                       dict(reason='use subagent delivery for this child session'))


def has_prompt_request(agent, request_id):
    def matches(message):
        source = message.get('source', {})
        return source.get('kind') == 'user' and source.get('rpcId') == request_id
    return (any(matches(message) for message in list(agent.inbox.nextTurn) + list(agent.inbox.nextStep)) or
            any(event['type'] == 'user/message' and matches(event['data']) for event in agent.session.snapshotEvents()))


def resolve_prompt_files(content, resolve):
    admitted, receipts = [], []
    for part in content:
        if part['type'] != 'file':
            admitted.append(part)
            continue
        ref = resolve(part['receiptId'])
        if ref is None:
            raise RemoteError('session/attachment-invalid', 'File was not uploaded for this session.', dict(reason='FILE_NOT_STAGED'))
        admitted.append(dict(type='file', attachment=ref))
        if part['receiptId'] not in receipts:
            receipts.append(part['receiptId'])
    return admitted, receipts


def referenced_image(events, attachment_id):
    def find(content):
        for part in content if isinstance(content, (list, tuple)) else []:
            if not isinstance(part, dict):
                continue
            if part.get('type') == 'image' and isinstance(part.get('attachment'), dict):
                if part['attachment'].get('attachmentId') == attachment_id:
                    return part['attachment']
            if part.get('type') == 'tool-result':
                result = find(part.get('content'))
                if result is not None:
                    return result
        return None
    for event in events:
        data = event['data']
        candidates = [data.get('content'), (data.get('message') or {}).get('content')]
        candidates.extend(part.get('content') for part in data.get('inserted', []))
        if event['type'] in ('assistant/message', 'assistant/attempt'):
            candidates.extend([chunk['block']] for chunk in assistantStreamChunks(data['stream'], 'block-end'))
        for content in candidates:
            found = find(content)
            if found is not None:
                return found
    return None


class CurrentSessionCommands:
    def __init__(self, ctx, agents, default_cwd=None):
        self.ctx, self.agents, self.default_cwd = ctx, agents, default_cwd

    async def resolve_agent(self, session_id):
        found = await self.agents.resolveAgent(session_id)
        if 'error' in found:
            raise found['error']
        return found['agent']

    async def prompt(self, request):
        if not has_prompt_content(request['content']):
            raise RemoteError('gateway/bad-request', 'prompt content must include non-whitespace text or an attachment', {})
        zone = canonical_client_time_zone(request['clientTimeZone']) if 'clientTimeZone' in request else None
        if 'clientTimeZone' in request and zone is None:
            raise RemoteError('session/invalid-time-zone', 'clientTimeZone must be UTC or a valid IANA Area/Location name', dict(value=request['clientTimeZone']))
        agent = await self.resolve_agent(request['sessionId'])
        if has_prompt_request(agent, request['requestId']):
            return dict(accepted=True)
        selected = self.agents.selectionFor(agent).current
        if not isinstance(selected, dict):
            selected = selected.to_dict()
        if not any(row['id'] == selected['provider'] for row in self.ctx.get('llm').listProviders()):
            raise RemoteError('session/model-unavailable', 'no adapter serves provider "{}"; select a model for this session'.format(selected['provider']),
                              dict(provider=selected['provider'], model=selected['model']))
        source = dict(kind='user', rpcId=request['requestId'])
        if zone is not None:
            source['clientTimeZone'] = zone
        has_image = any(part['type'] == 'image' for part in request['content'])
        async def admit():
            try:
                if has_image:
                    current = self.agents.selectionFor(agent).current
                    current = current if isinstance(current, dict) else current.to_dict()
                    model = await self.ctx.get('llm').resolveModelInfo(current['provider'], current['model'])
                    if 'inputModalities' in model and 'image' not in model['inputModalities']:
                        raise RemoteError('session/attachment-invalid', 'Model "{}" does not support image input.'.format(current['model']),
                                          dict(reason='MODEL_DOES_NOT_SUPPORT_IMAGES'))
                uploads = self.ctx.get('fileUploads')
                admitted, receipts = resolve_prompt_files(request['content'], lambda receipt: uploads.resolve(agent, receipt))
                content = await self.ctx.get('attachments').admitPromptContent(admitted)
                message = create_user_message(dict(content=content, source=source))
                if self.ctx.get('agents').get(agent.id) is not agent:
                    raise RemoteError('session/not-found', 'session "{}" was disposed during prompt admission'.format(agent.id), dict(sessionId=agent.id))
                binding = uploads.bindPrompt(agent, receipts, request['requestId'])
                try:
                    (agent.steer if request['mode'] == 'steer' else agent.followup)(message)
                    binding.commit()
                finally:
                    binding.dispose()
            except Exception as error:
                if remote_error_of(error) is not None:
                    raise
                if isinstance(error, AttachmentError):
                    raise RemoteError('session/attachment-invalid', error.message, dict(reason=error.code)) from None
                reason = getattr(error, 'name', 'Error') + ': ' + getattr(error, 'message', str(error))
                raise RemoteError('session/agent-busy', 'prompt rejected', dict(reason=reason)) from None
            return dict(accepted=True)
        return await self.agents.serializeImageAdmission(agent, admit) if has_image else await admit()

    def updateQueue(self, request):
        action, item_id = request['action'], request['itemId']
        if action['kind'] == 'edit':
            if any(part['type'] != 'text' for part in action['content']):
                raise RemoteError('session/attachment-invalid', 'queue edits accept text content only', dict(reason='QUEUE_EDIT_NON_TEXT'))
            if not has_prompt_content(action['content']):
                raise RemoteError('gateway/bad-request', 'queue edit content must include non-whitespace text', {})
        agent = self.ctx.get('agents').get(request['sessionId'])
        missing = lambda: RemoteError('session/queue-item-not-found', 'queued item is no longer pending', dict(itemId=item_id))
        if agent is None:
            raise missing()
        if has_subagent_owner(self.ctx, agent.session, agent):
            identity = self.ctx.get('sessionProjections').snapshot(agent.session, ['subagent'])['values'].get('subagent')
            if identity is None or identity['mode'] != 'continuable' or not agent.session.isOwnSeq(identity['seq']):
                raise ownership_error(request['sessionId'])
        located = next(((target, message) for target, messages in [('next-turn', agent.inbox.nextTurn), ('next-step', agent.inbox.nextStep)]
                        for message in messages if message['id'] == item_id), None)
        if located is None:
            raise missing()
        target, message = located
        if action['kind'] == 'steer' and (target != 'next-turn' or agent.status != 'running'):
            raise RemoteError('session/steer-unavailable', 'current turn no longer accepts steering', dict(itemId=item_id))
        if action['kind'] == 'edit':
            agent.inbox.replace(item_id, freeze_message(dict(message, content=list(action['content']))))
        elif action['kind'] == 'remove':
            agent.inbox.remove(item_id)
            source = message['source']
            if source['kind'] == 'user' and 'rpcId' in source:
                self.ctx.get('fileUploads').retirePrompt(agent, source['rpcId'])
        elif action['kind'] == 'steer':
            agent.inbox.remove(item_id)
            agent.steer(message)
        else:
            raise ValueError('unexpected queue action')
        return dict(accepted=True)

    def cancel(self, request):
        agent = self.ctx.get('agents').get(request['sessionId'])
        if agent is None:
            raise RemoteError('session/not-found', 'session "{}" not found (not attached)'.format(request['sessionId']), dict(sessionId=request['sessionId']))
        if has_subagent_owner(self.ctx, agent.session, agent):
            raise ownership_error(request['sessionId'])
        agent.cancel(dict(kind='user'), dict(keepInbox=True))
        return dict(accepted=True)

    async def attachment(self, request):
        sid = request['sessionId']
        try:
            attached = self.ctx.get('sessions').get(sid)
            if attached is not None:
                events = attached.snapshotEvents()
            else:
                observed = await self.ctx.get('sessionQuery').observeSession(sid, dict(projectionMode='none'))
                try:
                    if observed.header.cwd is None:
                        raise RemoteError('session/not-found', 'session "{}" not found'.format(sid), dict(sessionId=sid))
                    events = list(observed.events)
                finally:
                    observed.dispose()
        except Exception as error:
            if isinstance(error, SessionQueryError) and error.code == 'SESSION_QUERY_SESSION_NOT_FOUND':
                raise RemoteError('session/not-found', 'session "{}" not found'.format(sid), dict(sessionId=sid)) from None
            if remote_error_of(error) is not None:
                raise
            text = getattr(error, 'name', 'Error') + ': ' + str(error)
            raise RemoteError('gateway/internal', 'attachment authorization unavailable for session "{}": {}'.format(sid, text), {}) from None
        ref = referenced_image(events, request['attachmentId'])
        if ref is None:
            raise RemoteError('session/attachment-invalid', 'Image is not referenced by this session.', dict(reason='ATTACHMENT_NOT_REFERENCED'))
        try:
            stored = await self.ctx.get('attachments').readImage(ref)
            return dict(attachment=stored['ref'], data=base64.b64encode(stored['data']).decode('ascii'))
        except AttachmentError as error:
            raise RemoteError('session/attachment-invalid', error.message, dict(reason=error.code)) from None
        except Exception:
            raise RemoteError('gateway/internal', 'Unable to read image attachment.', {}) from None
