"""Lossless compact Assistant attempts and readers from the rc.3 LLM contract."""
import math

from dsh.core.session.json import UNDEFINED, deep_freeze, snapshot_json_value
from dsh.cordis.utils import js_to_string
from dsh.cordis.json_text import stringify_json
from dsh.cordis.text import has_non_whitespace as non_whitespace
from .assembler import BlockAssembler


def integer(value):
    return type(value) in (int, float) and abs(value) <= 9007199254740991 and math.isfinite(value) and int(value) == value


def safe_time(value):
    if not integer(value):
        raise TypeError('Assistant stream time must be a safe integer, got ' + js_to_string(value))
    return value


def safe_index(value, label):
    if not integer(value) or value < 0 or value == 0 and math.copysign(1, value) < 0:
        raise TypeError(label + ' index must be a non-negative safe integer')
    return value


def snapshot_chunk(chunk):
    value = snapshot_json_value(chunk, default=UNDEFINED)
    if value is UNDEFINED:
        raise TypeError('Assistant stream chunk must be losslessly JSON-serializable')
    return value


class AssistantStreamAccumulator:
    def __init__(self):
        self.records = []

    def push(self, value):
        time = safe_time(value.get('time', UNDEFINED))
        chunk = snapshot_chunk(value.get('chunk', UNDEFINED))
        timed = deep_freeze(dict(time=time, chunk=chunk))
        kind = chunk['type']
        previous = self.records[-1] if self.records else None
        if kind in ('text-delta', 'reasoning-delta', 'tool-call-delta'):
            safe_index(chunk.get('index', UNDEFINED), kind)
            if kind != 'tool-call-delta':
                if not isinstance(chunk.get('text'), str):
                    raise TypeError(kind + ' text must be a string')
                tag = 'text-chunks' if kind == 'text-delta' else 'reasoning-chunks'
                key, fragment = 'texts', chunk['text']
            else:
                if not isinstance(chunk.get('id'), str):
                    raise TypeError('tool-call-delta id must be a string')
                if 'name' in chunk and not isinstance(chunk['name'], str):
                    raise TypeError('tool-call-delta name must be a string')
                if not isinstance(chunk.get('argumentsDelta'), str):
                    raise TypeError('tool-call-delta argumentsDelta must be a string')
                if chunk['id'] == '' or chunk.get('name') == '':
                    self.records.append(dict(type='chunk', time=time, chunk=chunk))
                    return timed
                tag, key, fragment = 'tool-call-chunks', 'args', chunk['argumentsDelta']
            same = previous is not None and previous['type'] == tag and previous['index'] == chunk['index']
            gap = time - previous['lastTime'] if same else None
            same = same and integer(gap) and previous['lastTime'] + gap == time
            if kind == 'tool-call-delta' and same:
                same = previous['id'] == chunk['id'] and ('name' in previous) == ('name' in chunk) and previous.get('name') == chunk.get('name')
            if same:
                previous['dt'].append(gap)
                previous[key].append(fragment)
                previous['lastTime'] = time
            else:
                current = dict(type=tag, time0=time, index=chunk['index'], dt=[], lastTime=time)
                current[key] = [fragment]
                if kind == 'tool-call-delta':
                    current['id'] = chunk['id']
                    if 'name' in chunk:
                        current['name'] = chunk['name']
                self.records.append(current)
        elif kind in ('block-start', 'block-end', 'usage', 'finish'):
            self.records.append(dict(type='chunk', time=time, chunk=chunk))
        else:
            raise RuntimeError('unreachable variant in AssistantStreamAccumulator.push: ' + stringify_json(chunk))
        return timed

    def snapshot(self):
        result = []
        for value in self.records:
            if value['type'] == 'chunk':
                result.append(dict(value))
            else:
                record = {key: item for key, item in value.items() if key != 'lastTime'}
                record['dt'] = list(value['dt'])
                key = 'args' if value['type'] == 'tool-call-chunks' else 'texts'
                record[key] = list(value[key])
                result.append(record)
        return deep_freeze(result)


def exact_keys(value, keys, label):
    if len(value) != len(keys) or any(key not in value for key in keys):
        raise TypeError(label + ' Assistant stream record must contain exactly ' + ', '.join(keys))


def string_array(value, label):
    if not isinstance(value, list) or any(not isinstance(child, str) for child in value):
        raise TypeError(label + ' must be a string array')
    return value


def validate_record(value):
    if not isinstance(value, dict):
        raise TypeError('Assistant stream record must be an object')
    kind = value.get('type', UNDEFINED)
    if kind in ('text-chunks', 'reasoning-chunks', 'tool-call-chunks'):
        tool = kind == 'tool-call-chunks'
        keys = ['type', 'time0', 'index', 'dt', 'id'] + (['name'] if 'name' in value else []) + ['args'] if tool else ['type', 'time0', 'index', 'dt', 'texts']
        exact_keys(value, keys, kind)
        field = 'args' if tool else 'texts'
        fragments = string_array(value[field], kind + ' ' + field)
        if not fragments:
            raise TypeError(kind + ' ' + field + ' must be non-empty')
        if tool:
            if not isinstance(value['id'], str) or not value['id']:
                raise TypeError('tool-call-chunks id must be a non-empty string')
            if value.get('name', UNDEFINED) is not UNDEFINED and (not isinstance(value['name'], str) or not value['name']):
                raise TypeError('tool-call-chunks name must be a non-empty string')
        time = safe_time(value['time0'])
        safe_index(value['index'], kind)
        if not isinstance(value['dt'], list) or any(not integer(v) for v in value['dt']):
            raise TypeError(kind + ' dt must contain safe integers')
        if len(value['dt']) != len(fragments) - 1:
            raise TypeError(kind + ' dt length must be one less than its members')
        for gap in value['dt']:
            time += gap
            if not integer(time):
                raise TypeError(kind + ' member times must stay safe integers')
        return value
    if kind == 'chunk':
        exact_keys(value, ['type', 'time', 'chunk'], 'chunk')
        time = safe_time(value['time'])
        if not isinstance(value['chunk'], dict):
            raise TypeError('Assistant stream raw chunk must be a lossless JSON object')
        try:
            chunk = snapshot_chunk(value['chunk'])
        except Exception as error:
            failure = TypeError('Assistant stream raw chunk must be a lossless JSON object')
            failure.cause = error
            raise failure from error
        return deep_freeze(dict(type='chunk', time=time, chunk=chunk))
    rendered = 'undefined' if kind is UNDEFINED else stringify_json(kind)
    raise TypeError('Unsupported Assistant stream record ' + rendered)


def expandAssistantStream(stream):
    if not isinstance(stream, (list, str)):
        raise TypeError('stream is not iterable')
    chunks = []
    for candidate in stream:
        value = validate_record(candidate)
        kind = value['type']
        if kind == 'chunk':
            chunks.append(dict(time=value['time'], chunk=value['chunk']))
            continue
        field = 'args' if kind == 'tool-call-chunks' else 'texts'
        time = value['time0']
        for index, fragment in enumerate(value[field]):
            if index:
                time += value['dt'][index - 1]
            if kind == 'tool-call-chunks':
                chunk = dict(type='tool-call-delta', index=value['index'], id=value['id'], argumentsDelta=fragment)
                if 'name' in value:
                    chunk['name'] = value['name']
            else:
                chunk = dict(type='text-delta' if kind == 'text-chunks' else 'reasoning-delta', index=value['index'], text=fragment)
            chunks.append(dict(time=time, chunk=chunk))
    return chunks


def isTokenDelta(chunk):
    kind = chunk['type']
    if kind in ('text-delta', 'reasoning-delta'):
        return chunk['text'] != ''
    return kind == 'tool-call-delta' and (chunk['argumentsDelta'] != '' or chunk.get('name', UNDEFINED) is not UNDEFINED)


def isVisibleChunk(chunk):
    kind = chunk['type']
    if kind in ('text-delta', 'reasoning-delta'):
        return non_whitespace(chunk['text'])
    if kind == 'block-start':
        return chunk['blockType'] not in ('text', 'reasoning', 'tool-call')
    if kind == 'block-end':
        block = chunk['block']
        return non_whitespace(block['text']) if block['type'] in ('text', 'reasoning') else block['type'] != 'tool-call'
    return False


def chunkHasVisibleText(chunk):
    if chunk['type'] == 'text-delta':
        return non_whitespace(chunk['text'])
    return chunk['type'] == 'block-end' and chunk['block']['type'] == 'text' and non_whitespace(chunk['block']['text'])


def first_member_time(run, predicate):
    time = run['time0']
    for index, fragment in enumerate(run['args' if run['type'] == 'tool-call-chunks' else 'texts']):
        if index:
            time += run['dt'][index - 1]
        if predicate(fragment):
            return time
    return UNDEFINED


def runFirstTokenTime(run):
    if run['type'] == 'tool-call-chunks' and run.get('name', UNDEFINED) is not UNDEFINED:
        return run['time0']
    return first_member_time(run, lambda fragment: fragment != '')


def runFirstVisibleTime(run):
    return UNDEFINED if run['type'] == 'tool-call-chunks' else first_member_time(run, non_whitespace)


def assistantStreamFirstTokenTime(stream):
    for value in stream:
        time = (value['time'] if isTokenDelta(value['chunk']) else UNDEFINED) if value['type'] == 'chunk' else runFirstTokenTime(value)
        if time is not UNDEFINED:
            return time
    return UNDEFINED


def assistantStreamHasVisibleContent(stream):
    return any(isVisibleChunk(value['chunk']) if value['type'] == 'chunk' else runFirstVisibleTime(value) is not UNDEFINED for value in stream)


def assistantStreamHasVisibleText(stream):
    return any(any(non_whitespace(text) for text in value['texts']) if value['type'] == 'text-chunks' else value['type'] == 'chunk' and chunkHasVisibleText(value['chunk']) for value in stream)


def lastAssistantStreamChunk(stream, kind):
    return next((value['chunk'] for value in reversed(stream) if value['type'] == 'chunk' and value['chunk']['type'] == kind), UNDEFINED)


def assistantStreamChunks(stream, kind):
    return [value['chunk'] for value in stream if value['type'] == 'chunk' and value['chunk']['type'] == kind]


def joinAssistantStreamText(stream):
    return ''.join(''.join(value['texts']) if value['type'] == 'text-chunks' else value['chunk']['text'] if value['type'] == 'chunk' and value['chunk']['type'] == 'text-delta' else '' for value in stream)


def assembleAssistantStream(stream, assembler=None):
    assembler = assembler if assembler is not None else BlockAssembler()
    for value in stream:
        kind = value['type']
        if kind == 'chunk':
            assembler.push(value['chunk'])
        elif kind in ('text-chunks', 'reasoning-chunks'):
            assembler.push(dict(type='text-delta' if kind == 'text-chunks' else 'reasoning-delta', index=value['index'], text=''.join(value['texts'])))
        elif kind == 'tool-call-chunks':
            chunk = dict(type='tool-call-delta', index=value['index'], id=value['id'], argumentsDelta=''.join(value['args']))
            if value.get('name', UNDEFINED) is not UNDEFINED:
                chunk['name'] = value['name']
            assembler.push(chunk)
        else:
            raise RuntimeError('unreachable variant in assembleAssistantStream: ' + stringify_json(value))
    return assembler
