"""Actual file-upload service, command registry and Connection receipt journeys."""
import asyncio
import json
import os
import re
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from dsh.attachment.store_current import CurrentLocalAttachmentStore
from dsh.cordis.context import Context
from dsh.core.abort import AbortController
from dsh.core.scope import create_scope
from dsh.core.session.current_session import CurrentSession, CurrentSessionPlugin
from dsh.host.connection.current import CurrentHostConnection
from dsh.host.file_upload_current import CurrentFileUploads, FILE_UPLOAD_PATH
from dsh.interaction.commands_current import CurrentCommandRuntime


async def run(case):
    ctx = Context()
    live, agents, receipts, bindings, results, invocations, identities = {}, {}, [], {}, [], [], {}
    def normalize(value):
        if isinstance(value, str):
            def replace(match):
                raw = match.group()
                if raw not in identities:
                    identities[raw] = 'opaque:' + str(len(identities) + 1)
                return identities[raw]
            return re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|cmd-[0-9a-f]{8}-[1-9][0-9]*', replace, value)
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value
    with tempfile.TemporaryDirectory(prefix='rc3-upload-') as directory, patch.object(CurrentSession, '_event_time', return_value=1000):
        try:
            await ctx.plugin(CurrentSessionPlugin)
            ctx.set_service('agents', SimpleNamespace(get=lambda sid: live.get(sid)))
            store = CurrentLocalAttachmentStore(ctx, dict(dshHome=directory))
            connection = CurrentHostConnection(ctx, [], SimpleNamespace(is_authenticated=lambda _: True))
            await ctx.plugin(CurrentCommandRuntime)
            await ctx.plugin(CurrentFileUploads)
            uploads, commands = ctx.get('fileUploads'), ctx.get('commands')
            for sid in ('one', 'two', 'child'):
                class Agent:
                    pass
                agent = Agent()
                agent.id = sid
                agent.session = ctx.get('sessions').create(sid, dict(meta=dict(createdAt=1000, **(dict(origin='subagent') if sid == 'child' else {}))))
                agent.ctx = create_scope(ctx, agent).ctx
                live[sid] = agents[sid] = agent
            if case.get('sessionCommands'):
                from dsh.api.session_commands_current import CurrentSessionCommands, ownership_error
                from dsh.core.inbox_current import ReactLoopInbox
                from dsh.session.projections import SessionProjectionsPlugin
                await ctx.plugin(SessionProjectionsPlugin)
                ctx.get('agents').isOwnedBy = lambda *_: False
                ctx.get('sessionProjections').register(dict(key='subagent', stateVersion=1, stateSchema=lambda value: value,
                    init=lambda *_: case.get('identity'), apply=lambda state, _: state, wire=dict(viewSchema=lambda value: value, view=lambda value: value)))
                route = [True]
                async def model(*_args):
                    return dict(inputModalities=['text'] if case.get('textOnly') else ['text', 'image'])
                ctx.set_service('llm', SimpleNamespace(listProviders=lambda: [dict(id='fixture')] if route[0] else [], resolveModelInfo=model))
                for agent in agents.values():
                    agent.status = 'idle'
                    agent.inbox = ReactLoopInbox(ctx.get('sessionProjections'), agent.session, SimpleNamespace(emit=lambda *_: None))
                    def send(message, target, subject):
                        if case.get('rejectPrompt'):
                            raise RuntimeError('delivery refused')
                        subject.inbox.append(target, message)
                    agent.followup = lambda message, subject=agent: send(message, 'next-turn', subject)
                    agent.steer = lambda message, subject=agent: send(message, 'next-step', subject)
                    agent.cancel = lambda *_: None
                async def resolve_agent(sid):
                    agent = agents[sid]
                    return dict(error=ownership_error(sid)) if agent.session.header.origin == 'subagent' else dict(agent=agent)
                locks = {}
                async def serialize(agent, operation):
                    lock = locks.setdefault(agent, asyncio.Lock())
                    async with lock:
                        return await operation()
                controller = CurrentSessionCommands(ctx, SimpleNamespace(resolveAgent=resolve_agent,
                    selectionFor=lambda _: SimpleNamespace(current=dict(provider='fixture', model='model')),
                    serializeImageAdmission=serialize))
            def receipt(index):
                return receipts[index]['receiptId'] if isinstance(index, int) else index
            for action in case['actions']:
                try:
                    op = action['op']
                    agent = agents[action.get('agent', 'one')]
                    if op == 'prompt':
                        content = [dict(type='file', receiptId=receipt(part['receipt'])) if part['type'] == 'file' else part for part in action['content']]
                        value = await controller.prompt(dict(sessionId=agent.id, requestId=action.get('requestId', 'req-1'), mode=action.get('mode', 'queue'),
                            content=content, **({'clientTimeZone': action['clientTimeZone']} if 'clientTimeZone' in action else {})))
                    elif op == 'queue':
                        pending = list(agent.inbox.nextTurn) + list(agent.inbox.nextStep)
                        item_id = pending[action.get('index', 0)]['id'] if pending else 'missing'
                        value = controller.updateQueue(dict(sessionId=agent.id, itemId=item_id, action=action['action']))
                    elif op == 'appendQueued':
                        agent.inbox.append('next-turn', dict(id='seeded-message', role='user', content=[dict(type='text', text='seeded')],
                            source=dict(kind='user', rpcId='seeded-request')))
                        value = True
                    elif op == 'status':
                        agent.status = action['value']
                        value = True
                    elif op == 'route':
                        route[0] = action['value']
                        value = True
                    elif op == 'cancel':
                        value = controller.cancel(dict(sessionId=agent.id))
                    elif op == 'attachment':
                        attachment_id = action['attachmentId'] if 'attachmentId' in action else agent.inbox.nextTurn[0]['content'][0]['attachment']['attachmentId']
                        value = await controller.attachment(dict(sessionId=agent.id, attachmentId=attachment_id))
                    elif op == 'view':
                        value = dict(nextTurn=agent.inbox.nextTurn, nextStep=agent.inbox.nextStep, events=agent.session.snapshotEvents())
                    elif op == 'upload':
                        value = await uploads.upload(agent, dict(data=action.get('data', 'YQ=='), name=action.get('name', 'a.txt')), AbortController().signal)
                        receipts.append(value)
                    elif op == 'resolve':
                        value = uploads.resolve(agent, receipt(action.get('receipt', 0)))
                    elif op == 'bind':
                        binding = uploads.bindPrompt(agent, [receipt(index) for index in action['receipts']], action['requestId'])
                        bindings[action.get('binding', 'binding')] = binding
                        if action.get('commit'):
                            binding.commit()
                        value = True
                    elif op == 'rollback':
                        bindings[action.get('binding', 'binding')].dispose()
                        value = True
                    elif op == 'retire':
                        uploads.retirePrompt(agent, action['requestId'])
                        value = True
                    elif op == 'observe':
                        if case.get('sessionCommands'):
                            agent.session.append('user/message', dict(id='observed-' + str(agent.session.seq), role='user', content=[dict(type='text', text='accepted')],
                                source=dict(kind=action.get('kind', 'user'), rpcId=action['requestId'])), surface_op='append')
                        else:
                            agent.session.append_user_message('accepted', source=dict(kind=action.get('kind', 'user'), rpcId=action['requestId']))
                        value = True
                    elif op == 'drop':
                        live.pop(agent.id, None)
                        ctx.emit('session/disposed', agent.session)
                        value = True
                    elif op == 'resolver':
                        async def resolve(sid):
                            found = agents[action.get('target', 'two')]
                            live[sid] = found
                            return found
                        bindings['resolver'] = uploads.registerAgentResolver(resolve)
                        value = True
                    elif op == 'http':
                        async def chunks():
                            for chunk in action.get('chunks', []):
                                yield bytes.fromhex(chunk)
                        url = 'http://host' + action.get('path', FILE_UPLOAD_PATH)
                        shared = connection.createSharedFetchHandler('/api')
                        request = dict(url=url, path=url.split('?', 1)[0][len('http://host'):], method=action.get('verb', 'POST'),
                            headers={'content-type': action.get('contentType', 'application/octet-stream')}, body=chunks(), signal=AbortController().signal)
                        response = await shared.fetch(request)
                        body = response['body']
                        if response.get('headers', {}).get('content-type', '').startswith('application/json'):
                            body = json.loads(body)
                            if body.get('ok'):
                                receipts.append(body['value'])
                        value = dict(mode=shared.requestBodyMode(request), status=response['status'], body=body)
                    elif op == 'register':
                        def handler(invocation):
                            invocations.append(dict(rawInput=invocation.rawInput, attachments=invocation.attachments))
                            return dict(kind='success', text='command accepted')
                        commands.register(dict(name='files', description='file command', handler=handler,
                            **({'input': action['input']} if 'input' in action else {})))
                        value = commands.remoteList(agent)
                    elif op == 'execute':
                        submitted = [dict(type='file', receiptId=receipt(index)) if not isinstance(index, dict) else index for index in action.get('attachments', [])]
                        execution = await commands.execute(agent, '/files note', submitted, AbortController().signal)
                        value = dict(commandId=execution.command_id, result=execution.result) if execution is not None else None
                    else:
                        raise RuntimeError('Unknown upload action: ' + op)
                    results.append(dict(outcome='value', value=normalize(value)))
                except Exception as error:
                    results.append(dict(outcome='error', error=normalize(dict(name=getattr(error, 'name', 'TypeError' if isinstance(error, TypeError) else 'Error'),
                        message=getattr(error, 'message', str(error)), **(dict(code=error.code, details=error.details) if hasattr(error, 'details') else {})))))
            return dict(results=results, invocations=normalize(invocations))
        finally:
            await ctx.fiber.dispose()
            for parent, _, files in os.walk(directory):
                for name in files:
                    os.chmod(os.path.join(parent, name), 0o600)


def execute(case):
    return asyncio.run(run(case))
