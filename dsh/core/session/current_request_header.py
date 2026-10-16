"""v3 request epochs: system prompts belong to message history."""
from dsh.core.session.request_header import header_equals as _header_equals


def canonicalHeader(header):
    result = dict(config=header['config'])
    defaults = header.get('adapterDefaults')
    if isinstance(defaults, dict) and (defaults.get('reasoningEffort') is True or defaults.get('maxTokens') is True):
        result['adapterDefaults'] = defaults
    tools = header.get('tools')
    if tools is not None and len(tools):
        result['tools'] = tools
    return result


def headerEquals(left, right):
    # The old shared config/schema comparator sees only the three v3 fields.
    return _header_equals({key:left[key] for key in ('config','adapterDefaults','tools') if key in left},
                          {key:right[key] for key in ('config','adapterDefaults','tools') if key in right})


def foldRequestHeader(events, initial=None):
    state = initial
    for event in events:
        if event['type'] == 'request/header':
            state = canonicalHeader(event['data']['header'])
    return state
