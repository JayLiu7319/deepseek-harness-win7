"""rc.3 prompt, queue and attachment commands over explicit Agent ownership."""
import base64
import uuid

from dsh.attachment.error import AttachmentError
from dsh.cordis.text import trim_js
from dsh.cordis.errors import ThrownValueError
from dsh.cordis.utils import js_to_string
from dsh.core.session.types import SessionSeq
from dsh.llm.message import create_user_message, freeze_message
from dsh.llm.assistant_stream import assistantStreamChunks
from dsh.session.session_query import SessionQueryError
from dsh.typert.remote import RemoteError, remote_error_of
from dsh.util_time import canonical_client_time_zone


def has_prompt_content(content):
    return any(part['type'] != 'text' or trim_js(part['text']) for part in content)


def error_text(error):
    if isinstance(error, ThrownValueError):
        return js_to_string(error.value)
    return getattr(error, 'name', 'Error') + ': ' + getattr(error, 'message', str(error))


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

    async def create(self, request):
        from dsh.api.session_agents_current import ApiSessionPresetConflict, ApiSessionCwdConflict, ApiSessionSubagentOwnership
        if 'workspaceId' in request and 'cwd' in request:
            raise RemoteError('gateway/bad-request', 'session.create accepts workspaceId or cwd, not both', {})
        sid = request.get('sessionId', 'session-' + str(uuid.uuid4()))
        workspace = None
        if 'workspaceId' in request:
            workspace = self.ctx.get('workspaceRegistry').get(request['workspaceId'])
            if workspace is None:
                raise RemoteError('workspace/not-found', 'workspace "{}" not found'.format(request['workspaceId']), dict(workspaceId=request['workspaceId']))
        cwd = workspace.path if workspace is not None else request.get('cwd', self.default_cwd)
        try:
            agent = await self.agents.ensureSession(sid, cwd, 'sessionId' in request, request.get('agentPreset'))
        except Exception as error:
            if remote_error_of(error) is not None:
                raise
            if isinstance(error, ApiSessionPresetConflict):
                details = dict(sessionId=error.sessionId, requestedPreset=error.requestedPreset)
                if error.existingPreset is not None:
                    details['existingPreset'] = error.existingPreset
                raise RemoteError('agent-preset/conflict', str(error), details) from None
            if isinstance(error, ApiSessionCwdConflict):
                details = dict(sessionId=error.sessionId, requestedCwd=error.requestedCwd)
                if error.existingCwd is not None:
                    details['existingCwd'] = error.existingCwd
                raise RemoteError('session/conflict', str(error), details) from None
            if isinstance(error, ApiSessionSubagentOwnership):
                raise ownership_error(error.sessionId) from None
            raise RemoteError('gateway/internal', 'failed to create session "{}": {}'.format(sid, error_text(error)), {}) from None
        if workspace is not None:
            try:
                await workspace.attachSession(sid)
            except Exception as error:
                raise RemoteError('session/workspace-attach-failed', 'session "{}" was created but could not attach to workspace "{}": {}'.format(sid, workspace.id, error_text(error)), dict(sessionId=sid, workspaceId=workspace.id)) from None
        preset = self.agents.presetForSession(agent.session)
        return dict(sessionId=sid, **(dict(agentPreset=preset) if preset is not None else {}))

    async def selectModel(self, request):
        agent = await self.resolve_agent(request['sessionId'])
        async def select():
            try:
                resolved = await self.ctx.get('llm').resolveCallConfig({key: request[key] for key in ('provider', 'model', 'reasoningEffort') if key in request})
                selected = {key: resolved[key] for key in ('provider', 'model', 'reasoningEffort') if key in resolved}
                self.agents.selectForNextRequest(agent, selected)
                try:
                    await self.ctx.get('agentDefaultModel').saveSelection(selected)
                except Exception as error:
                    self.ctx.logger.warn('session-controller: model selection changed for the Session but the default was not saved: ' + error_text(error))
                return dict(selected=dict(selected))
            except Exception as error:
                if remote_error_of(error) is not None:
                    raise
                message = js_to_string(error.value) if isinstance(error, ThrownValueError) else getattr(error, 'message', str(error))
                raise RemoteError('session/model-unavailable', message, dict(provider=request['provider'], model=request['model'])) from None
        return await self.agents.serializeImageAdmission(agent, select)

    async def rename(self, request):
        from dsh.session.canonical_title import SessionTitleInvalidError
        agent = await self.resolve_agent(request['sessionId'])
        titles = self.ctx.get('sessionTitle')
        if titles is None:
            raise RemoteError('gateway/internal', 'renaming is unavailable: this deployment mounts no session-title service', {})
        try:
            accepted = titles.rename(agent.session, request['title'])
            return dict(title=accepted['title'], seq=accepted['eventSeq'])
        except SessionTitleInvalidError as error:
            raise RemoteError('session/title-invalid', str(error), dict(sessionId=request['sessionId'])) from None
        except Exception as error:
            raise RemoteError('gateway/internal', 'failed to rename session "{}": {}'.format(request['sessionId'], error_text(error)), {}) from None

    async def fork(self, request):
        try:
            at_seq = SessionSeq(request['atSeq']) if 'atSeq' in request else None
        except (ValueError, TypeError):
            raise RemoteError('gateway/bad-request', 'atSeq must be a non-negative safe integer', {}) from None
        sid = request['sessionId']
        try:
            source = await self.ctx.get('sessionQuery').observeSession(sid)
        except SessionQueryError as error:
            if error.code == 'SESSION_QUERY_SESSION_NOT_FOUND':
                raise RemoteError('session/not-found', 'session "{}" not found'.format(sid), dict(sessionId=sid)) from None
            raise RemoteError('gateway/internal', 'fork source unavailable for session "{}": {}'.format(sid, error_text(error)), {}) from None
        except Exception as error:
            raise RemoteError('gateway/internal', 'fork source unavailable for session "{}": {}'.format(sid, error_text(error)), {}) from None
        try:
            last_seq = source.events[-1]['seq'] if source.events else -1
            boundary = next((event for event in source.events if event['type'] == 'turn/end' and at_seq is not None and event['seq'] >= at_seq), None)
            if boundary is None and (at_seq is None or at_seq > last_seq):
                boundary = next((event for event in reversed(source.events) if event['type'] == 'turn/end'), None)
            if boundary is None:
                message = ('session "{}" has not completed the turn containing event {}'.format(sid, js_to_string(at_seq))
                    if at_seq is not None and at_seq <= last_seq else 'session "{}" has no completed turn to fork from'.format(sid))
                raise RemoteError('session/fork-unavailable', message, dict(sessionId=sid))
            cut = boundary['seq'] + 1
            while cut < len(source.events) and source.events[cut]['type'] != 'turn/start':
                cut += 1
            try:
                workspace = await self.fork_workspace(source.header)
            except Exception as error:
                raise RemoteError('gateway/internal', 'failed to resolve fork workspace for session "{}": {}'.format(sid, error_text(error)), {}) from None
            child_id = 'session-' + str(uuid.uuid4())
            composition = await self.agents.composeAgent(self.agents.presetForObservation(source))
            try:
                model = self.ctx.get('agentDefaultModel').currentSelection()
                meta = dict(parentSession=source.header.id, isSeeded=True)
                if source.header.cwd is not None:
                    meta['cwd'] = source.header.cwd
                if 'agentPreset' in composition:
                    meta['agentPreset'] = composition['agentPreset']
                await self.ctx.get('agents').create(dict(sessionId=child_id, seed=list(source.events[:cut]), inheritedEventCount=cut,
                    meta=meta, agentOptions=dict(provider=model['provider'], model=model['model']), setup=composition['setup']))
            except Exception as error:
                raise RemoteError('gateway/internal', 'failed to fork session "{}": {}'.format(sid, error_text(error)), {}) from None
            if workspace is not None:
                try:
                    await workspace.attachSession(child_id)
                except Exception as error:
                    raise RemoteError('session/workspace-attach-failed', 'session "{}" was forked but could not attach to workspace "{}": {}'.format(child_id, workspace.id, error_text(error)), dict(sessionId=child_id, workspaceId=workspace.id)) from None
            return dict(sessionId=child_id)
        finally:
            source.dispose()

    async def fork_workspace(self, header):
        workspaces = self.ctx.get('workspaceRegistry').list()
        direct = next((workspace for workspace in workspaces if header.id in workspace.sessionIds), None)
        if direct is not None or header.origin != 'subagent':
            return direct
        lineage = await self.ctx.get('sessionQuery').traceSession(header.id)
        for ancestor in lineage['ancestors']:
            found = next((workspace for workspace in workspaces if ancestor['header'].id in workspace.sessionIds), None)
            if found is not None:
                return found
        return None

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
        from dsh.api.session_agents_current import inspect_api_session, ApiSessionNotFound
        sid = request['sessionId']
        try:
            attached = self.ctx.get('sessions').get(sid)
            if attached is not None:
                events = attached.snapshotEvents()
            else:
                events = (await inspect_api_session(self.ctx, sid))['events']
        except Exception as error:
            if isinstance(error, ApiSessionNotFound):
                raise RemoteError('session/not-found', 'session "{}" not found'.format(sid), dict(sessionId=sid)) from None
            raise RemoteError('gateway/internal', 'attachment authorization unavailable for session "{}": {}'.format(sid, error_text(error)), {}) from None
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
