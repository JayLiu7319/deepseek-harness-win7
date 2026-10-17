"""Explicit logical-export inputs; expected values are frozen separately."""
import copy
import json
from pathlib import Path


def generate():
    cases = []
    header = dict(version=3, id='root', createdAt=1, isSeeded=False)
    logs = dict(root=dict(header=header, events=[]))
    def add(name, operation='serialize', **values):
        cases.append(dict(case='log-export/' + name, kind='log-export-current', operation=operation,
                          logs=copy.deepcopy(logs), **values))
    add('empty')
    for key, value in dict(cwd='C:/项目', parentSession='parent', origin='subagent', delegationDepth=2,
                           agentPreset=dict(name='standard'), seedLength=4, unknown='ignored').items():
        logs['root']['header'] = dict(header, **{key: value})
        add('header-' + key)
    logs['root']['header'] = header
    logs['root']['events'] = [dict(type='opaque', seq=0, time=1.5, ignorable=True,
                                  data={'10': 'ten', '2': 'two', 'text': '汉字\ud800', 'number': 1.0})]
    add('json-text')
    for signal in (False, True):
        add('read-' + str(signal), 'read', signal=signal)
    add('missing', 'read', id='missing')
    for key in ('openError', 'readError', 'closeError'):
        add(key, 'read', **{key: 'secret host path'})
    add('close-over-read-error', 'read', readError='read denied', closeError='close denied')
    logs['root']['events'] = []
    add('entries-empty', 'entries')
    def ref(kind, identity, name=None):
        value = dict(attachmentId=identity, mediaType='image/png' if kind == 'image' else 'text/plain', byteLength=3)
        if name is not None:
            value['name'] = name
        return dict(type=kind, attachment=value)
    image = ref('image', 'image-one')
    for index, name in enumerate(('a/b\\c\x00\x7f.txt', '.', '..', '', '正常文件.txt')):
        files = [ref('file', 'sha256:abcdef', name), ref('file', 'sha256:abcdef', 'another.txt')]
        content = [image, dict(type='tool-result', content=files + [image])]
        logs['root']['events'] = [dict(type='message', data=dict(content=content))]
        add('file-name-' + str(index), 'entries')
    for carrier in ('message', 'inserted', 'stream'):
        content = [image, ref('file', 'sha256:abcdef', 'stream.txt')]
        data = {'message': dict(content=content)} if carrier == 'message' else (
            {'inserted': [dict(content=content)]} if carrier == 'inserted' else
            {'stream': [dict(type='chunk', chunk=dict(type='block-end', block=block)) for block in content]})
        logs['root']['events'] = [dict(type='message', data=data)]
        add('carrier-' + carrier, 'entries')
    logs['child'] = dict(header=dict(header, id='child', isSeeded=True, parentSession='root'), events=[])
    node = lambda sid, children=[]: dict(session=dict(header=dict(id=sid)), descendants=children)
    add('descendants', 'entries', includeDescendants=True, live=['child'],
        descendants=[node('root'), node('child', [node('child')]), node('child')])
    add('missing-descendant', 'entries', includeDescendants=True, descendants=[node('absent')])
    return cases


if __name__ == '__main__':
    Path(__file__).with_name('log_export_current_cases.json').write_text(
        json.dumps(generate(), ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
