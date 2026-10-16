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
            def receipt(index):
                return receipts[index]['receiptId'] if isinstance(index, int) else index
            for action in case['actions']:
                try:
                    op = action['op']
                    agent = agents[action.get('agent', 'one')]
                    if op == 'upload':
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
