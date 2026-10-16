"""Canonical typed chunk assembly, shared by durable stream consumers.

The legacy agent-loop adapter remains separate until its typed request migration.
"""
from dsh.core.session.json import UNDEFINED
from dsh.cordis.json_text import stringify_json
from dsh.cordis.text import has_non_whitespace


class BlockAssembler:
    def __init__(self):
        self.partials = {}
        self.order = []
        self.usage = UNDEFINED
        self._finish = UNDEFINED
        self._replay = UNDEFINED

    def ensure(self, index, kind):
        if index not in self.partials:
            self.order.append(index)
            self.partials[index] = dict(blockType=kind, text='', toolCallArguments='')
        return self.partials[index]

    def push(self, chunk):
        kind = chunk['type']
        if kind == 'block-start':
            self.ensure(chunk['index'], chunk['blockType'])
        elif kind in ('text-delta', 'reasoning-delta'):
            part = self.ensure(chunk['index'], 'text' if kind == 'text-delta' else 'reasoning')
            if 'block' not in part:
                part['text'] += chunk['text']
        elif kind == 'tool-call-delta':
            part = self.ensure(chunk['index'], 'tool-call')
            if 'block' not in part:
                part['toolCallId'] = chunk['id']
                if chunk.get('name'):
                    part['toolCallName'] = chunk['name']
                part['toolCallArguments'] += chunk['argumentsDelta']
        elif kind == 'block-end':
            part = self.ensure(chunk['index'], chunk['block']['type'])
            if 'block' not in part:
                part['block'] = chunk['block']
        elif kind == 'usage':
            self.usage = chunk['usage']
        elif kind == 'finish':
            self._finish = chunk['reason']
            self._replay = chunk.get('replayState', UNDEFINED)
        else:
            raise RuntimeError('unreachable variant in BlockAssembler.push: ' + stringify_json(chunk))

    def assemble(self, part, index):
        if 'block' in part:
            return part['block']
        kind = part['blockType']
        if kind in ('text', 'reasoning'):
            return dict(type=kind, text=part['text'])
        if kind == 'tool-call':
            return dict(type=kind, id=part.get('toolCallId', 'call-%s' % index), name=part.get('toolCallName', ''), arguments=part['toolCallArguments'])
        raise RuntimeError('cannot assemble incomplete block of type "%s"' % kind)

    @property
    def finish(self):
        return dict(kind='stop') if self._finish is UNDEFINED else self._finish

    def assembled(self):
        all_blocks = [self.assemble(self.partials[index], index) for index in self.order]
        kept = [block['type'] != 'tool-call' for block in all_blocks] if self.finish['kind'] == 'max-tokens' else None
        blocks = all_blocks if kept is None else [block for block, keep in zip(all_blocks, kept) if keep]
        envelope = self._replay
        if envelope is UNDEFINED or envelope.get('blocks', UNDEFINED) is UNDEFINED:
            return blocks, envelope
        if len(envelope['blocks']) != len(all_blocks):
            return blocks, UNDEFINED
        if kept is None or len(blocks) == len(all_blocks):
            return blocks, envelope
        return blocks, dict(response=envelope['response'], blocks=[block for block, keep in zip(envelope['blocks'], kept) if keep])

    def blocks(self):
        return self.assembled()[0]

    def interruptedBlocks(self):
        blocks = []
        for index in self.order:
            part = self.partials[index]
            kind = part['block']['type'] if 'block' in part else part['blockType']
            if kind in ('text', 'reasoning'):
                block = self.assemble(part, index)
                if has_non_whitespace(block['text']):
                    blocks.append(block)
        return blocks

    @property
    def replayState(self):
        return self.assembled()[1]
