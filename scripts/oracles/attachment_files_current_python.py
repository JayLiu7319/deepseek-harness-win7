"""Observe actual current file storage and attachment admission."""
import asyncio
import hashlib
import os
import stat
import tempfile
from pathlib import Path

from dsh.attachment.files_current import file_leaf_name, stored_file_path, stored_file_object_path
from dsh.attachment.store_current import CurrentAttachmentStore, CurrentLocalAttachmentStore
from dsh.core.abort import AbortController


def failure(error):
    return dict(name=getattr(error, 'name', 'Error'), message=getattr(error, 'message', str(error)),
                **({'code': error.code} if hasattr(error, 'code') else {}))


async def run(case):
    with tempfile.TemporaryDirectory(prefix='rc3-files-') as directory:
        store = CurrentLocalAttachmentStore(config={'dshHome': directory})
        refs, results = [], []
        try:
            for action in case['actions']:
                try:
                    op = action['op']
                    if op == 'name':
                        value = file_leaf_name(action.get('value'))
                    elif op in ('save', 'stream', 'encoded', 'concurrent'):
                        controller = AbortController()
                        async def chunks():
                            for index, item in enumerate(action.get('chunks', [])):
                                if index == action.get('abortAt'):
                                    controller.abort(RuntimeError('upload cancelled'))
                                yield bytes.fromhex(item)
                            if action.get('fail'):
                                raise RuntimeError('source failed')
                        input_data = dict(**({'name': action['name']} if 'name' in action else {}))
                        if op == 'encoded':
                            value = await store.admitEncodedFile(dict(input_data, data=action['data']))
                        elif op == 'stream':
                            value = await store.saveFileStream(dict(input_data, data=chunks(), signal=controller.signal))
                        elif op == 'concurrent':
                            value = await asyncio.gather(*(store.saveFile(dict(data=bytes.fromhex(action['hex']), name=name))
                                for name in action['names']))
                            refs.extend(value)
                        else:
                            raw = bytes(index % 251 for index in range(action['size'])) if 'size' in action else bytes.fromhex(action['hex'])
                            value = await store.saveFile(dict(input_data, data=raw))
                        if op != 'concurrent':
                            refs.append(value)
                    elif op == 'path':
                        ref = action.get('ref', refs[action.get('index', 0)] if refs else {})
                        value = store.fileHostPath(ref).replace(store.root, '<root>').replace('\\', '/')
                    elif op == 'inspect':
                        ref = refs[action.get('index', 0)]
                        alias = store.fileHostPath(ref)
                        canonical = stored_file_object_path(store.root, ref['attachmentId'][7:])
                        facts, object_facts = os.stat(alias), os.stat(canonical)
                        value = dict(sameObject=facts.st_ino == object_facts.st_ino,
                            readOnly=not bool(facts.st_mode & stat.S_IWUSR),
                            staging=sorted(os.listdir(os.path.join(store.root, 'tmp'))))
                    elif op == 'mutate':
                        path = store.fileHostPath(refs[action.get('index', 0)])
                        os.chmod(path, 0o600)
                        Path(path).write_bytes(bytes.fromhex(action['hex']))
                        value = True
                    elif op in ('read', 'readMissing'):
                        ref = dict(action.get('ref', refs[action.get('index', 0)] if refs else {}))
                        if 'bytes' in action:
                            ref['bytes'] = action['bytes']
                        controller = AbortController()
                        if action.get('before'):
                            controller.abort(RuntimeError('read cancelled'))
                        data = bytearray()
                        sizes = []
                        try:
                            async for chunk in store.readFileStream(ref, controller.signal):
                                sizes.append(len(chunk))
                                data.extend(chunk)
                                if action.get('during'):
                                    controller.abort(RuntimeError('read cancelled'))
                            value = (dict(digest=hashlib.sha256(data).hexdigest(), bytes=len(data), maxChunk=max(sizes, default=0))
                                     if action.get('summary') else dict(hex=data.hex(), maxChunk=max(sizes, default=0)))
                        except Exception as error:
                            value = dict(error=failure(error), delivered=data.hex())
                    elif op == 'staging':
                        staging = Path(store.root) / 'tmp'
                        value = sorted(path.name for path in staging.iterdir()) if staging.exists() else []
                    elif op == 'base':
                        class Base(CurrentAttachmentStore):
                            async def saveImages(self, inputs):
                                self.inputs = inputs
                                return [dict(attachmentId='image-' + str(index)) for index, _ in enumerate(inputs)]
                        base = Base()
                        base.inputs = []
                        operation = action['method']
                        if operation == 'admitPromptContent':
                            value = dict(content=await base.admitPromptContent(action['content']),
                                images=[dict(item, data=item['data'].hex()) for item in base.inputs])
                        elif operation == 'readFileStream':
                            value = [chunk async for chunk in base.readFileStream({})]
                        else:
                            value = await getattr(base, operation)({})
                    else:
                        raise ValueError('Unknown file action: ' + op)
                    results.append(dict(outcome='value', value=value))
                except Exception as error:
                    results.append(dict(outcome='error', error=failure(error)))
            return dict(results=results)
        finally:
            # All names/links here were created by this owned temporary actor.
            # Unlock only its files so Python 3.8 can remove NTFS read-only names.
            for parent, _, files in os.walk(directory):
                for name in files:
                    os.chmod(os.path.join(parent, name), 0o600)


def execute(case):
    return asyncio.run(run(case))
