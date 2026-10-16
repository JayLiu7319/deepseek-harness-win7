"""Current browser control errors and explicit Queue/Steer delivery."""
import json

from dsh.attachment.error import AttachmentError
from dsh.core.session.json import UNDEFINED
from dsh.subagent.errors import SubagentError
from dsh.typert.remote import RemoteError
from dsh.util_time import canonical_client_time_zone


def validate(method, payload):
    issues = []
    keys = ['parentSessionId'] + (['childSessionId', 'mode'] if method != 'subagent.list' else [])
    if method == 'subagent.prompt':
        keys.append('delivery')
    for key in keys:
        value = payload.get(key, UNDEFINED)
        if key in ('mode', 'delivery'):
            choices = ['continuable'] if key == 'mode' else ['queue', 'steer']
            if value not in choices:
                issues.append(dict(code='invalid_value', values=choices, path=[key],
                    message='Invalid input: expected "continuable"' if key == 'mode' else 'Invalid option: expected one of "queue"|"steer"'))
        elif not isinstance(value, str):
            received = ('undefined' if value is UNDEFINED else 'null' if value is None else 'boolean' if type(value) is bool
                        else 'number' if type(value) in (int, float) else 'array' if isinstance(value, list) else 'object')
            issues.append(dict(expected='string', code='invalid_type', path=[key], message='Invalid input: expected string, received ' + received))
        elif not value:
            issues.append(dict(origin='string', code='too_small', minimum=1, inclusive=True, path=[key],
                               message='Too small: expected string to have >=1 characters'))
    if issues:
        raise RemoteError('gateway/bad-request', 'invalid payload for ' + method, dict(issues=issues))


def cancellation(error, signal):
    return signal.aborted or isinstance(error, SubagentError) and error.code == 'CANCELLED'


def reject_prompt(error, child, signal):
    if cancellation(error, signal):
        raise RemoteError('gateway/cancelled', 'subagent prompt was cancelled', {}, error)
    if isinstance(error, AttachmentError) or isinstance(error, SubagentError) and error.code == 'MODEL_DOES_NOT_SUPPORT_IMAGES':
        raise RemoteError('subagent/attachment-invalid', error.message, dict(reason=error.code), error)
    if isinstance(error, SubagentError):
        code, message = {
            'NOT_RESUMABLE': ('not-resumable', 'subagent cannot be resumed'),
            'UNAUTHORIZED': ('unauthorized', 'subagent does not belong to this parent'),
            **{key: ('delivery-unavailable', 'subagent follow-up is temporarily unavailable') for key in
               ('DRAINING', 'ACTIVATION_CLOSING', 'CONTINUATION_UNAVAILABLE', 'PERSISTENCE_UNAVAILABLE')},
        }.get(error.code, (None, None))
        if code is not None:
            raise RemoteError('subagent/' + code, message, dict(childSessionId=child), error)
    raise RemoteError('gateway/internal', 'subagent prompt failed', {}, error)


async def catalog(service, parent, signal):
    validate('subagent.list', dict(parentSessionId=parent))
    try:
        entries = await service.listChildren(parent, signal)
        agents = service.ctx.get('agents')
        rows = []
        for entry in entries:
            if entry['kind'] == 'child':
                child = agents.get(entry['id']) if agents is not None else None
                entry = dict(entry, activity='running' if child is not None and child.status == 'running' else 'inactive')
            rows.append(entry)
        return dict(entries=rows, parentAvailable=agents is not None and agents.get(parent) is not None)
    except Exception as error:
        if cancellation(error, signal):
            raise RemoteError('gateway/cancelled', 'subagent catalog read was cancelled', {}, error)
        if isinstance(error, SubagentError) and error.code == 'SUBAGENT_CONTROL_PROJECTIONS_UNAVAILABLE':
            raise RemoteError('subagent/projections-unavailable', 'subagent catalog is unavailable: this deployment does not mount the sessionProjections registry (load @deepseek-ai/dsh-session-projection)', {}, error)
        raise RemoteError('gateway/internal', 'subagent catalog read failed', {}, error)


async def prompt(service, request, signal):
    validate('subagent.prompt', request)
    zone = canonical_client_time_zone(request['clientTimeZone']) if 'clientTimeZone' in request else None
    if 'clientTimeZone' in request and zone is None:
        raise RemoteError('subagent/invalid-time-zone', 'clientTimeZone must be UTC or a valid IANA Area/Location name', dict(value=request['clientTimeZone']))
    agents = service.ctx.get('agents')
    parent = agents.get(request['parentSessionId']) if agents is not None else None
    if parent is None:
        raise RemoteError('subagent/parent-unavailable', 'parent session {} is not live'.format(json.dumps(request['parentSessionId'])), dict(parentSessionId=request['parentSessionId']))
    source = dict(kind='user', rpcId=request['requestId'])
    if zone is not None:
        source['clientTimeZone'] = zone
    try:
        parts = request['content']
        if all(part['type'] == 'text' for part in parts):
            content = [dict(type='text', text=part['text']) for part in parts]
        else:
            attachments = service.ctx.get('attachments')
            if attachments is None:
                raise RuntimeError('subagent image prompt requires an attachment store')
            content = await attachments.admitPromptContent(parts)
        identity = await service._deliver_prompt(parent, request['childSessionId'], content, source, signal, request['delivery'])
        return dict(messageId=identity)
    except Exception as error:
        reject_prompt(error, request['childSessionId'], signal)


def interrupt(service, child, parent, mode):
    validate('subagent.interrupt', dict(parentSessionId=parent, childSessionId=child, mode=mode))
    try:
        service.interrupt(child, dict(kind='user', parentSessionId=parent))
    except Exception as error:
        if isinstance(error, SubagentError) and error.code == 'UNAUTHORIZED':
            raise RemoteError('subagent/unauthorized', 'subagent does not belong to this parent', dict(childSessionId=child), error)
        raise RemoteError('gateway/internal', 'subagent interrupt failed', {}, error)
    return dict(accepted=True)
