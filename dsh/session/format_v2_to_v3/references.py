"""Only audited same-artifact coordinates change during system-message promotion."""
from dsh.core.session.json import UNDEFINED
from dsh.session.format import SessionFormatError, sessionFormatCount
from .payload import record


def remapEvent(event, seq, mapping):
    def one(value):
        source = sessionFormatCount(value, 'source event reference')
        if source >= event['seq'] or source >= len(mapping):
            raise SessionFormatError('reference must name an earlier source event')
        return mapping[int(source)]
    def numbers(value):
        if not isinstance(value, list):
            raise SessionFormatError('sequence references must be an array')
        return [one(v) for v in value]
    def span(value):
        value = record(value, 'sequence range')
        return dict(value, start=one(value.get('start', UNDEFINED)), end=one(value.get('end', UNDEFINED)))
    data = record(event['data'], event['type'])
    if event['type'] == 'command/done' and data.get('sourceEventSeq', UNDEFINED) is not UNDEFINED:
        data = dict(data, sourceEventSeq=one(data['sourceEventSeq']))
    elif event['type'] in ('compaction/summary', 'compaction/prune'):
        data = dict(data, shadowedRange=span(data.get('shadowedRange', UNDEFINED)), shadowedSeqs=numbers(data.get('shadowedSeqs', UNDEFINED)))
    elif event['type'] in ('session/title', 'session/title-llm-request'):
        data = dict(data, messageSeqs=numbers(data.get('messageSeqs', UNDEFINED)))
    target = dict(event, seq=seq, data=data)
    if event.get('sourceEventSeqs', UNDEFINED) is not UNDEFINED:
        target['sourceEventSeqs'] = numbers(event['sourceEventSeqs'])
    if event.get('surfaceOp', UNDEFINED) is not UNDEFINED and event['surfaceOp'] != 'append':
        target['surfaceOp'] = span(event['surfaceOp'])
    return target
