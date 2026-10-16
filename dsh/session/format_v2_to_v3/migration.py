"""Promote changed request prompts into protected, durable system messages."""
import hashlib

from dsh.core.session.json import UNDEFINED
from dsh.cordis.utils import _js_strict_equal
from dsh.session.format import SessionFormatError, SessionFormatUnsupportedMigrationError, defineSessionFormatMigration, sessionFormatCount
from dsh.session.format.chain import member, call
from dsh.session.format_v0_to_v1.payload import compact
from dsh.session.format_v1_to_v2 import assertReleasedV2Header
from .payload import assertEvent, canonicalizeTransformedEvent, record, SURFACE_TYPES
from .references import remapEvent
from .validation import assertReleasedV3Header


class ReleasedV2ToV3Stage:
    def __init__(self, source):
        self.input = source
        self.header = member(source, 'sourceHeader')
        assertReleasedV2Header(self.header)
        self.mapping, self.original_ids, self.generated_ids = [], set(), set()
        self.target_seq = 0
        self.source_cut = UNDEFINED if self.header['isSeeded'] else 0
        self.target_cut = UNDEFINED if self.header['isSeeded'] else 0
        if not self.header['isSeeded']:
            self.headerInheritedEventCount = 0
        self.foreign_delivery = UNDEFINED
        self.step, self.head, self.prompt = None, UNDEFINED, ''

    def transformEvent(self, event, context):
        if not _js_strict_equal(event.get('seq', UNDEFINED), len(self.mapping)):
            raise SessionFormatError('format v2 source events must be dense')
        assertEvent(event, 2)
        self.observe_message_ids(event)
        source = event
        data = record(event['data'], event['type'])
        if event['type'] == 'request/header':
            header = record(data['header'], 'request header')
            system = header.get('system')
            prompt = system if isinstance(system, str) else ''
            if prompt != self.prompt:
                self.emit_system(prompt, event, context)
            source = dict(event, data=dict(data, header={key: value for key, value in header.items() if key != 'system'}))
        if event['type'] in SURFACE_TYPES and self.head is UNDEFINED:
            raise SessionFormatUnsupportedMigrationError('format v2 surface before first step cannot acquire a system head without changing chronology')
        if event['type'] == 'session/end-seed' and data.get('inherited') is True:
            if not self.header['isSeeded']:
                raise SessionFormatError('format v2 unseeded Session contains an inherited end-seed marker')
            self.source_cut, self.target_cut = event['seq'], self.target_seq
        if event['type'] == 'session-log-deepseek/delivery-accepted':
            version = data.get('sessionFormatVersion', UNDEFINED)
            if _js_strict_equal(version, 3):
                raise SessionFormatError('format v2 delivery marker claims target format v3')
            if _js_strict_equal(version, 2) and data.get('sessionId') != self.header['id']:
                self.foreign_delivery = event['seq']
        target = remapEvent(source, self.target_seq, self.mapping)
        self.mapping.append(self.target_seq)
        self.target_seq += 1
        call(context, 'emitEvent', canonicalizeTransformedEvent(renamePtcEvent(target)))
        if event['type'] == 'step/start':
            self.step = dict(turn=data['turn'], step=data['step'])
            if self.head is UNDEFINED:
                self.emit_system('', event, context)
        elif event['type'] in ('step/end', 'turn/end'):
            self.step = None

    def transformRun(self, run, context):
        for event in call(run, 'expand'):
            self.transformEvent(event, context)

    def finish(self, context):
        cut = sessionFormatCount(self.source_cut, 'format v2 inherited end-seed marker')
        supplied = member(self.input, 'sourceInheritedEventCount')
        if supplied is not UNDEFINED and not _js_strict_equal(supplied, cut):
            raise SessionFormatError('format v2 inherited end-seed marker disagrees with its source cut')
        if self.foreign_delivery is not UNDEFINED and (self.header.get('parentSession', UNDEFINED) is UNDEFINED or self.foreign_delivery >= cut):
            raise SessionFormatError('current-generation delivery marker names the wrong Session')
        return sessionFormatCount(self.target_cut, 'format v3 inherited event count')

    def observe_message_ids(self, event):
        kind = event['type']
        data = record(event['data'], kind)
        messages = [data] if kind == 'user/message' else [record(data['message'], 'message')] if kind in ('assistant/message', 'tool/result') else data['inserted'] if kind == 'agent/inbox/spliced' else data['messages'] if kind == 'session/title-llm-request' else []
        for message in messages:
            identity = message['id']
            if identity in self.generated_ids:
                raise SessionFormatUnsupportedMigrationError('source message id collides with a generated system message id')
            self.original_ids.add(identity)

    def emit_system(self, prompt, anchor, context):
        if self.step is None:
            raise SessionFormatUnsupportedMigrationError('format v2 changed request prompt outside an open step cannot retain source chronology')
        identity = compact(['session-format-v2-to-v3', self.header['id'], anchor['seq'], anchor['type']])
        identity = 'v2-to-v3-system-' + hashlib.sha256(identity.encode('utf-8')).hexdigest()
        if identity in self.original_ids or identity in self.generated_ids:
            raise SessionFormatUnsupportedMigrationError('generated system message id collides with an existing message id')
        self.generated_ids.add(identity)
        seq = self.target_seq
        self.target_seq += 1
        event = dict(type='system/message', seq=seq, time=anchor['time'], data=dict(self.step,
            message=dict(id=identity, role='system', source=dict(kind='plugin', plugin='@deepseek-ai/dsh-system-prompt'), content=[] if prompt == '' else [dict(type='text', text=prompt)])))
        if self.head is UNDEFINED:
            event['surfaceOp'] = 'append'
        else:
            event.update(surfaceOp=dict(op='replace', start=self.head, end=self.head), sourceEventSeqs=[self.head])
        call(context, 'emitEvent', canonicalizeTransformedEvent(event))
        self.head, self.prompt = seq, prompt


def rename_message_source(message):
    source = message['source']
    if source.get('kind') == 'plugin' and source.get('plugin') == 'tools-code-mode':
        return dict(message, source=dict(source, plugin='tools-ptc'))
    return message


def renamePtcEvent(event):
    kind = event['type']
    if kind == 'agent-preset/selected' and event['data'].get('agentPreset') == 'code':
        return dict(event, data=dict(event['data'], agentPreset='ptc'))
    if kind in ('tool/code-dispatch-start', 'tool/code-dispatch'):
        return dict(event, type='tool/ptc-' + kind.split('tool/code-')[1])
    if kind == 'user/message':
        data = rename_message_source(event['data'])
        return event if data is event['data'] else dict(event, data=data)
    if kind in ('agent/inbox/spliced', 'session/title-llm-request'):
        data = event['data']
        key = 'inserted' if kind == 'agent/inbox/spliced' else 'messages'
        renamed = [rename_message_source(message) for message in data[key]]
        return event if all(a is b for a, b in zip(renamed, data[key])) else dict(event, data=dict(data, **{key:renamed}))
    return event


def migrate_header(header):
    assertReleasedV2Header(header)
    value = dict(header, version=3)
    if header.get('agentPreset') == 'code':
        value['agentPreset'] = 'ptc'
    return value


sessionFormatV2ToV3 = defineSessionFormatMigration(dict(name='@deepseek-ai/dsh-session-format-v2-to-v3',
    fromVersion=2, toVersion=3, migrateHeader=migrate_header, createStage=ReleasedV2ToV3Stage,
    validateTargetHeader=assertReleasedV3Header))
