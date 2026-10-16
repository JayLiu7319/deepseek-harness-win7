"""Canonical v3 admission, shared by the format catalog and Session integration.

The adjacent format libraries own historical semantics. These checks own the
installed Session boundary, where ordinary plugin payload additions stay open.
"""
import math

from dsh.core.session.json import UNDEFINED
from dsh.core.session.types import ALLOWED_ENVELOPE_KEYS, validate_session_header, assert_adapter_defaults

SESSION_FORMAT_VERSION = 3
SURFACE_EVENT_TYPES = frozenset(('system/message', 'user/message', 'assistant/message', 'tool/result'))


def safe(value, nonnegative=False, reject_negative_zero=False):
    return (type(value) in (int, float) and math.isfinite(value) and abs(value) <= 9007199254740991
        and int(value) == value and (not nonnegative or value >= 0)
        and (not reject_negative_zero or value != 0 or math.copysign(1, value) > 0))


def has_provider_model(value):
    return isinstance(value, dict) and all(isinstance(value.get(key), str) and value[key] for key in ('provider', 'model'))


def validateSessionEventData(event, subject):
    data = event.get('data', UNDEFINED)
    if event['type'] == 'request/header':
        if not isinstance(data, dict):
            raise ValueError(subject + ' data must be an object')
        header = data.get('header')
        if not isinstance(header, dict):
            raise ValueError(subject + ' header must be an object')
        if 'system' in header:
            raise ValueError(subject + ' must omit header.system; use system/message')
        if isinstance(header.get('tools'), list) and not header['tools']:
            raise ValueError(subject + ' must omit empty tools')
        if isinstance(header.get('adapterDefaults'), dict) and not header['adapterDefaults']:
            raise ValueError(subject + ' must omit empty adapterDefaults')
    elif event['type'] == 'tool/result':
        if not isinstance(data, dict):
            raise ValueError(subject + ' data must be an object')
        if data.get('error', UNDEFINED) is UNDEFINED:
            return
        message = data.get('message')
        content = message.get('content') if isinstance(message, dict) else None
        block = content[0] if isinstance(content, list) and content else None
        if not isinstance(block, dict) or block.get('isError') is not True:
            raise ValueError(subject + ' error requires message content[0].isError === true')


def assertMessageEventShape(event, subject):
    kind = event['type']
    if kind not in SURFACE_EVENT_TYPES:
        return
    data = event.get('data')
    message = data if kind == 'user/message' else data.get('message') if isinstance(data, dict) else None
    if not isinstance(message, dict) or not isinstance(message.get('id'), str) or not message['id']:
        raise ValueError(subject + ' lacks an identified message')
    role = 'system' if kind == 'system/message' else 'assistant' if kind == 'assistant/message' else 'user'
    if message.get('role') != role:
        raise ValueError(subject + ' message must have role "' + role + '"')
    source = message.get('source')
    if not isinstance(source, dict) or not isinstance(source.get('kind'), str) or not source['kind']:
        raise ValueError(subject + ' message has invalid source')
    content = message.get('content')
    if not isinstance(content, list):
        raise ValueError(subject + ' message has invalid content')
    if kind == 'system/message':
        if source['kind'] != 'plugin' or not isinstance(source.get('plugin'), str) or not source['plugin']:
            raise ValueError(subject + ' message must have plugin source')
    elif kind == 'assistant/message':
        if source['kind'] != 'model' or not has_provider_model(source):
            raise ValueError(subject + ' message must have model source')
    elif kind == 'tool/result':
        if source['kind'] != 'tool' or not isinstance(source.get('callId'), str) or not source['callId']:
            raise ValueError(subject + ' message must have tool source')
        if len(content) != 1 or not isinstance(content[0], dict) or content[0].get('type') != 'tool-result' or not isinstance(content[0].get('content'), list):
            raise ValueError(subject + ' message must contain one tool-result block')
        if content[0].get('toolCallId') != source['callId']:
            raise ValueError(subject + ' message has mismatched tool call ids')


def assertCurrentLlmShape(event, index):
    kind, data = event['type'], event['data']
    subject = 'seed %s at index %s' % (kind, index)
    if kind == 'request/header':
        header = data['header']
        config = header.get('config')
        if not has_provider_model(config):
            raise ValueError(subject + ' lacks provider/model')
        effort = config.get('reasoningEffort', UNDEFINED)
        if effort is not UNDEFINED and (not isinstance(effort, str) or not effort):
            raise ValueError(subject + ' has an invalid reasoningEffort')
        assert_adapter_defaults(header.get('adapterDefaults', UNDEFINED), config, index)
        if data.get('reason') not in ('initial', 'resume', 'change', 'series'):
            raise ValueError(subject + ' has an invalid reason')
        if data.get('startsSeries', UNDEFINED) is not UNDEFINED and data['startsSeries'] is not True:
            raise ValueError(subject + ' has an invalid startsSeries marker')
    if kind in SURFACE_EVENT_TYPES:
        assertMessageEventShape(event, subject)
    if kind in ('assistant/message', 'assistant/attempt'):
        if not isinstance(data, dict) or not all(safe(data.get(key), True, True) for key in ('turn', 'step')) or not isinstance(data.get('stream'), list):
            raise ValueError(subject + ' has invalid settlement fields')


def assertSessionEventEnvelope(event, index):
    invalid = ValueError('seed event at index %s has an invalid event envelope' % index)
    if (not isinstance(event, dict) or any(key not in ALLOWED_ENVELOPE_KEYS for key in event)
        or not isinstance(event.get('type'), str) or not safe(event.get('seq'), True, True)
        or not safe(event.get('time')) or event.get('data', UNDEFINED) is UNDEFINED
        or event.get('ignorable', UNDEFINED) is not UNDEFINED and event['ignorable'] is not True):
        raise invalid
    validateSessionEventData(event, 'seed %s at index %s' % (event['type'], index))
    if event['type'] in SURFACE_EVENT_TYPES or event['type'] in ('request/header', 'assistant/attempt'):
        assertCurrentLlmShape(event, index)


def validateCurrentHeader(header):
    return validate_session_header(header.get('id', UNDEFINED), header, expected_version=3)
