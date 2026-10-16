"""Released cross-event relationships; open recovery tails are intentionally admitted."""
from dsh.core.session.json import UNDEFINED
from dsh.session.format import SessionFormatError
from .codec import record
from .payload import compact, equal_json
from .validation import RELEASED_V0_EVENT_DISPOSITIONS, SURFACE_TYPES

REPAIR_TEXT = 'The tool call was interrupted before the Harness recorded it as started. Retry it if it is still needed.'


def require_step(event, data, turn, step):
    if turn is None or step is None or data.get('turn') != turn or data.get('step') != step:
        raise SessionFormatError(event['type'] + ' does not match an open turn and step')


def no_tools(lifecycles, boundary):
    if lifecycles:
        raise SessionFormatError(boundary + ' leaves unresolved tool call ' + next(iter(lifecycles)))


def exact_repair(event, blocks, error):
    data = event['data']
    message = data['message']
    call_id = message['source']['callId']
    block = blocks[0] if blocks else {}
    nested = block.get('content', [])
    return (error.get('name') == 'ToolNotStartedError' and error.get('code') == 'TOOL_NOT_STARTED'
        and event.get('sourceEventSeqs', UNDEFINED) is UNDEFINED
        and message['id'] == 'interrupted-tool-result-%s-%s' % (call_id, event['seq'])
        and block.get('isError') is True and len(nested) == 1
        and nested[0].get('type') == 'text' and nested[0].get('text') == REPAIR_TEXT)


def apply_surface(surface, event):
    operation = event.get('surfaceOp', UNDEFINED)
    if operation is UNDEFINED:
        raise SessionFormatError(event['type'] + ' requires a surfaceOp marker')
    if operation == 'append':
        return surface + [event['seq']]
    start = surface.index(operation['start']) if operation['start'] in surface else -1
    end = surface.index(operation['end']) if operation['end'] in surface else -1
    if start < 0 or end < start:
        raise SessionFormatError(event['type'] + ' replacement range is not on the current surface')
    sources = event.get('sourceEventSeqs', [])
    if not isinstance(sources, list):
        sources = []
    if any(seq not in sources for seq in surface[start:end + 1]):
        raise SessionFormatError(event['type'] + ' replacement sourceEventSeqs omit a shadowed surface node')
    return surface[:start] + [event['seq']] + surface[end + 1:]


def title_sources(events, event, data, validate_text):
    seqs = data['messageSeqs']
    if event['type'] == 'session/title':
        source = record(data['source'], 'session/title %s source' % event['seq'])
        if (len(seqs) == 0) != (source['kind'] == 'user'):
            raise SessionFormatError('session/title %s messageSeqs must be empty exactly for a user title' % event['seq'])
    selected = []
    for seq in seqs:
        source = events[int(seq)] if 0 <= seq < len(events) else None
        label = '%s %s messageSeqs must cite earlier human user/message events' % (event['type'], event['seq'])
        if source is None or source['type'] != 'user/message':
            raise SessionFormatError(label)
        source_data = record(source['data'], '%s %s data' % (source['type'], seq))
        provenance = record(source_data['source'], '%s %s source' % (source['type'], seq))
        if provenance['kind'] != 'user':
            raise SessionFormatError(label)
        selected.append(dict(seq=seq, text='\n'.join(block['text'] for block in source_data['content'] if block.get('type') == 'text' and isinstance(block.get('text'), str))))
    if event['type'] == 'session/title-llm-request':
        messages = data['messages']
        message = messages[0] if messages else {}
        blocks = message.get('content', [])
        source = record(message['source'], 'session/title-llm-request message source') if message else {}
        label = 'session/title-llm-request messages do not represent messageSeqs'
        if len(messages) != 1 or message.get('role') != 'user' or len(blocks) != 1 or source.get('kind') != 'plugin' or source.get('plugin') != 'dsh-session-title-llm':
            raise SessionFormatError(label)
        expected = 'Generate the session title from this JSON array of human messages:\n' + compact(selected)
        if blocks[0].get('type') != 'text' or validate_text and blocks[0].get('text') != expected:
            raise SessionFormatError(label)


def compaction_owner(opened, data, kind):
    if opened is None or data.get('compactionId', UNDEFINED) != opened['id'] or data.get('sourceCommandId', UNDEFINED) != opened.get('sourceCommandId', UNDEFINED):
        raise SessionFormatError(kind + ' has no matching compaction/start')


def compaction_turn(owner, turn, kind):
    if owner != turn:
        raise SessionFormatError(kind + ' does not match the open turn')


def surface_span(surface, data, kind):
    span = data['shadowedRange']
    start = surface.index(span['start']) if span['start'] in surface else -1
    end = surface.index(span['end']) if span['end'] in surface else -1
    expected = [] if start < 0 or end < start else surface[start:end + 1]
    if not equal_json(expected, data['shadowedSeqs']):
        raise SessionFormatError(kind + ' shadowedSeqs do not name an exact current surface span')


def assertReleasedArtifactRelationships(artifact, extensions=None):
    extensions = extensions or {}
    turn, step, provider = None, None, UNDEFINED
    next_turn, next_step = 1, 1
    surface, compaction = [], None
    stale, opened = set(), None
    events = artifact['events']
    for event in events:
        if event['type'] == 'compaction/start':
            opened = event['seq']
        elif event['type'] == 'compaction/end':
            opened = None
        elif event['type'] == 'session/end-seed':
            if opened is not None:
                stale.add(opened)
            opened = None
    retries, retry_starts, ptc_roots, ptc_starts, tools, commands = [], set(), {}, {}, {}, set()
    for event in events:
        kind, seq = event['type'], event['seq']
        extension_step = kind in extensions.get('stepEvents', ())
        if kind not in RELEASED_V0_EVENT_DISPOSITIONS and not extension_step:
            continue
        data = record(event['data'], '%s %s data' % (kind, seq))
        if kind in SURFACE_TYPES:
            surface = apply_surface(surface, event)
        if kind in ('turn/start', 'turn/end') and compaction is not None and compaction['startSeq'] not in stale:
            raise SessionFormatError(kind + ' crosses an open compaction')
        if extension_step:
            require_step(event, data, turn, step)
            continue
        if kind == 'turn/start':
            previous = events[int(seq) - 1] if seq > 0 else {}
            if (extensions.get('legacyInterruptedTurnRestart') is True and turn is not None and step is None
                    and data['turn'] == turn + 1 and next_turn == turn and previous.get('type') == 'agent/inbox/spliced'):
                splice = record(previous['data'], 'agent/inbox/spliced %s data' % previous['seq'])
                if splice.get('target') == 'next-turn' and isinstance(splice.get('inserted'), list) and splice['inserted']:
                    turn = None
                    next_turn += 1
            if turn is not None or data['turn'] != next_turn:
                raise SessionFormatError('turn/start %s does not open expected turn %s' % (compact(data['turn']), next_turn))
            turn, step, next_step = data['turn'], None, 1
            tools.clear()
        elif kind == 'turn/end':
            if turn != data['turn']:
                raise SessionFormatError('turn/end %s has no matching open turn' % compact(data['turn']))
            no_tools(tools, 'turn/end')
            if step is not None:
                raise SessionFormatError('turn/end %s crosses an open step' % compact(data['turn']))
            turn = None
            next_turn += 1
        elif kind == 'step/start':
            if turn != data['turn'] or step is not None or data['step'] != next_step:
                raise SessionFormatError(kind + ' does not match the open turn and next step')
            step = data['step']
        elif kind == 'step/end':
            require_step(event, data, turn, step)
            no_tools(tools, 'step/end')
            tools.clear()
            step = None
            next_step += 1
        elif kind in ('assistant/chunk', 'assistant/message', 'tool/call'):
            require_step(event, data, turn, step)
            if kind == 'assistant/message':
                message = record(data['message'], 'assistant/message %s message' % seq)
                for block in message['content']:
                    if block['type'] != 'tool-call':
                        continue
                    call_id = block['id']
                    if call_id in tools:
                        raise SessionFormatError('assistant/message repeats advertised tool call ' + call_id)
                    tools[call_id] = dict(name=block['name'], arguments=block['arguments'], state='advertised')
            elif kind == 'tool/call':
                call_id = data['callId']
                lifecycle = tools.get(call_id)
                if lifecycle is None or lifecycle['state'] != 'advertised' or lifecycle['name'] != data['name'] or lifecycle['arguments'] != data['arguments']:
                    raise SessionFormatError('tool/call ' + call_id + ' does not match one advertised tool call')
                lifecycle['state'] = 'started'
        elif kind == 'tool/result':
            if event.get('surfaceOp') == 'append':
                require_step(event, data, turn, step)
                message = record(data['message'], 'tool/result %s message' % seq)
                source = record(message['source'], 'tool/result %s source' % seq)
                call_id = source['callId']
                error = {} if 'error' not in data else record(data['error'], 'tool/result %s error' % seq)
                lifecycle = tools.get(call_id)
                if lifecycle is None:
                    raise SessionFormatError('tool/result ' + call_id + ' has no advertised tool lifecycle')
                if lifecycle['state'] == 'advertised' and not exact_repair(event, message['content'], error):
                    raise SessionFormatError('tool/result ' + call_id + ' is not the exact TOOL_NOT_STARTED repair')
                del tools[call_id]
            elif turn is None:
                raise SessionFormatError('tool/result replacement is outside an open turn')
        elif kind in ('request/header', 'request/context'):
            if turn is None:
                raise SessionFormatError(kind + ' is outside an open turn')
            if kind == 'request/header':
                provider = data['header']['config']['provider']
        elif kind in ('tool/code-dispatch-start', 'tool/code-dispatch'):
            if turn is None:
                raise SessionFormatError(kind + ' is outside an open turn')
            root, parent, child = data['rootCallId'], data['parentCallId'], data['subCallId']
            if child in ptc_roots and ptc_roots[child] != root:
                raise SessionFormatError(kind + ' changes its rootCallId')
            if parent != root and ptc_roots.get(parent) != root:
                raise SessionFormatError(kind + ' parentCallId does not belong to rootCallId')
            if kind == 'tool/code-dispatch-start':
                if child in ptc_starts:
                    raise SessionFormatError('tool/code-dispatch-start repeats subCallId')
                ptc_starts[child] = dict(root=root, parent=parent, name=data['name'], arguments=data['arguments'], settled=False)
            else:
                start = ptc_starts.get(child)
                if start is None or start['settled']:
                    raise SessionFormatError('tool/code-dispatch has no unique start')
                if start['root'] != root or start['parent'] != parent or start['name'] != data['name'] or not equal_json(start['arguments'], data['arguments']):
                    raise SessionFormatError('tool/code-dispatch does not match its start')
                start['settled'] = True
            ptc_roots[child] = root
        elif kind == 'llm/retry':
            if turn != data['turn'] or data['step'] != (step if step is not None else next_step - 1) or turn is None:
                raise SessionFormatError('llm/retry does not match the current turn and step')
            if data['provider'] != provider:
                raise SessionFormatError('llm/retry provider does not match the open request/header')
            prior = next((v for v in reversed(retries) if all(v['data'][key] == data[key] for key in ['turn', 'step', 'provider', 'policyKey'])), None)
            expected = (prior['data']['retry'] if prior else 0) + 1
            if data['retry'] != expected:
                raise SessionFormatError('llm/retry must use retry %s' % expected)
            if prior and prior['data']['retryId'] != data['retryId']:
                raise SessionFormatError('llm/retry must preserve retryId across one policy chain')
            if prior is None and any(v['data']['retryId'] == data['retryId'] for v in retries):
                raise SessionFormatError('llm/retry reuses retryId %s across policy chains' % compact(data['retryId']))
            retries.append(event)
        elif kind == 'llm/retry-started':
            scheduled = next((v for v in retries if v['data']['retryId'] == data['retryId'] and v['data']['retry'] == data['retry']), None)
            if scheduled is None:
                raise SessionFormatError('llm/retry-started pairs no prior scheduled attempt')
            if scheduled['data']['turn'] != data['turn'] or scheduled['data']['step'] != data['step']:
                raise SessionFormatError('llm/retry-started does not match its scheduled turn and step')
            key = (data['retryId'], data['retry'])
            if key in retry_starts:
                raise SessionFormatError('llm/retry-started repeats one scheduled attempt')
            retry_starts.add(key)
        elif kind in ('session/title', 'session/title-llm-request'):
            title_sources(events, event, data, extensions.get('preservedSourceTitleRequestText') is not True)
        elif kind == 'command/run':
            command_id = data['commandId']
            if command_id in commands:
                raise SessionFormatError('command/run repeats commandId ' + command_id)
            commands.add(command_id)
        elif kind == 'command/done':
            command_id = data['commandId']
            if command_id not in commands:
                raise SessionFormatError('command/done ' + command_id + ' has no prior command/run')
            if 'sourceEventSeq' in data:
                n = data['sourceEventSeq']
                source = events[int(n)] if 0 <= n < len(events) else {}
                if data['kind'] != 'success' or source.get('type') in ('command/run', 'command/done'):
                    raise SessionFormatError('command/done ' + command_id + ' has invalid sourceEventSeq')
        elif kind == 'session-log-deepseek/delivery-accepted':
            accepted = data.get('sessionFormatVersion')
            accepted = 0 if accepted is None else accepted
            if accepted == artifact['header']['version']:
                inherited = 'parentSession' in artifact['header'] and seq < artifact['inheritedEventCount']
                if not inherited and data['sessionId'] != artifact['header']['id']:
                    raise SessionFormatError('current-generation delivery marker names the wrong Session')
        elif kind == 'compaction/start':
            if compaction is not None:
                raise SessionFormatError('compaction/start overlaps an open compaction')
            compaction_turn(data['turn'], turn, kind)
            compaction = dict(id=data['compactionId'], sourceCommandId=data.get('sourceCommandId', UNDEFINED), turn=data['turn'], startSeq=seq, summarized=False)
        elif kind == 'compaction/summary':
            compaction_owner(compaction, data, kind)
            compaction_turn(compaction['turn'], turn, kind)
            if compaction['summarized']:
                raise SessionFormatError('compaction/summary repeats')
            surface_span(surface, data, kind)
            compaction = dict(compaction, summarized=True)
        elif kind == 'compaction/end':
            compaction_owner(compaction, data, kind)
            if data['turn'] != compaction['turn']:
                raise SessionFormatError('compaction/end changes its owner turn')
            compaction_turn(compaction['turn'], turn, kind)
            if data.get('error', UNDEFINED) is UNDEFINED and not compaction['summarized']:
                raise SessionFormatError('successful compaction/end requires one summary')
            compaction = None
        elif kind == 'compaction/prune':
            surface_span(surface, data, kind)
        elif kind == 'user/message':
            source = record(data['source'], 'user/message %s source' % seq)
            if event.get('surfaceOp') != 'append' and source.get('kind') == 'plugin' and source.get('plugin') == 'compact':
                compaction_owner(compaction, source, 'compaction checkpoint at seq %s' % seq)
        elif kind == 'session/end-seed':
            compaction = None
