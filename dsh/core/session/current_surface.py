"""Canonical v3 surface transitions and protected system-head ownership."""
from dsh.core.session.json import UNDEFINED
from dsh.core.surface import _assert_tool_result_rewrite
from .current import safe, SURFACE_EVENT_TYPES
from .current_vocabulary import KNOWN_SESSION_EVENT_TYPES


def provenance(event, shadowed):
    raw, seq = event.get('sourceEventSeqs', UNDEFINED), event['seq']
    if event['type'] == 'assistant/message' and raw is not UNDEFINED:
        raise ValueError('assistant/message embeds its source stream and cannot carry sourceEventSeqs')
    sources = set()
    if raw is not UNDEFINED:
        if not isinstance(raw, list):
            raise ValueError('sourceEventSeqs on event at seq %s must be an array when present' % seq)
        if not raw:
            raise ValueError('sourceEventSeqs must not be empty')
        non_earlier = None
        for value in raw:
            if not safe(value, True):
                raise ValueError('session event "%s" sourceEventSeqs must densely contain non-negative safe integers' % event['type'])
            sources.add(value)
            if non_earlier is None and value >= seq:
                non_earlier = value
        if len(sources) != len(raw):
            raise ValueError('sourceEventSeqs must not contain duplicates')
        if non_earlier is not None:
            raise ValueError('sourceEventSeqs must reference earlier events: %s >= current seq %s' % (non_earlier, seq))
    missing = [seq for seq in shadowed if seq not in sources]
    if missing:
        raise ValueError('surface replace: sourceEventSeqs must include every shadowed surface node; missing ' + ', '.join(str(seq) for seq in missing))


def validateSurfaceMetadata(event):
    kind = event['type']
    if kind not in SURFACE_EVENT_TYPES:
        if kind not in KNOWN_SESSION_EVENT_TYPES and event.get('ignorable') is True:
            return None
        for key in ('surfaceOp', 'sourceEventSeqs'):
            if event.get(key, UNDEFINED) is not UNDEFINED:
                raise ValueError('session event "%s" is not surface-eligible and cannot carry %s' % (kind, key))
        return None
    operation = event.get('surfaceOp', UNDEFINED)
    if operation is UNDEFINED:
        raise ValueError('session event "%s" is surface-eligible and requires a surfaceOp marker' % kind)
    if operation != 'append':
        if not isinstance(operation, dict):
            raise ValueError('session event "%s" carries an invalid surfaceOp' % kind)
        if (set(operation) != {'op', 'startSeq', 'endSeq'} or operation['op'] != 'replace'
                or not safe(operation['startSeq'], True) or not safe(operation['endSeq'], True)):
            raise ValueError('session event "%s" carries an invalid replace surfaceOp' % kind)
        if operation['startSeq'] >= event['seq'] or operation['endSeq'] >= event['seq']:
            raise ValueError('surface replace at seq %s: startSeq and endSeq must reference earlier events' % event['seq'])
    provenance(event, [])
    return operation


class CurrentSurface:
    def __init__(self, events, base_seq=0):
        self.events, self.base_seq = events, base_seq
        self.nodes, self.replaceGeneration = [], 0

    def plan(self, event, expected):
        if type(event['seq']) not in (int, float) or event['seq'] != expected:
            raise ValueError('session event seq %s is not contiguous; expected %s' % (event['seq'], expected))
        operation = validateSurfaceMetadata(event)
        if operation is None or operation == 'append':
            return operation
        start, end = operation['startSeq'], operation['endSeq']
        if start not in self.nodes:
            raise ValueError('surface replace: start seq %s not found in surface' % start)
        if end not in self.nodes:
            raise ValueError('surface replace: end seq %s not found in surface' % end)
        first, last = self.nodes.index(start), self.nodes.index(end)
        if first > last:
            raise ValueError('surface replace: start seq %s (index %s) is after end seq %s (index %s)' % (start, first, end, last))
        shadowed = self.nodes[first:last+1]
        provenance(event, shadowed)
        _assert_tool_result_rewrite(event, shadowed, self.events, self.base_seq)
        if first == 0 and self.events[int(self.nodes[0]-self.base_seq)]['type'] == 'system/message' and (event['type'] != 'system/message' or len(shadowed) != 1):
            raise ValueError('surface replace: node 0 holds the system prompt and may be rewritten only by a system/message over exactly that node')
        return first, last

    def apply(self, event, plan):
        if plan == 'append':
            self.nodes.append(event['seq'])
        elif plan is not None:
            first, last = plan
            self.nodes[first:last+1] = [event['seq']]
            self.replaceGeneration += 1


def deriveEventMessage(event):
    kind, data = event['type'], event['data']
    if kind == 'user/message':
        return data
    if kind in ('system/message', 'assistant/message'):
        return data['message'] if data['message']['content'] else None
    if kind == 'tool/result':
        return data['message']
    return None
