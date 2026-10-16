"""Exercise installed-current admission with actual v3 restoration inputs and corruptions."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    cases = {}
    def add(operation, **inputs):
        digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()[:20]
        name = operation + '/' + digest
        cases[name] = dict(case=name, kind='session-catalog', operation=operation, **inputs)

    source = json.loads((ROOT/'scripts/oracles/session_v3_logical_cases.json').read_text(encoding='utf-8'))
    for case in source:
        if case['operation'] == 'restore':
            add('currentArtifact', artifact=case['artifact'])
    header = dict(version=3, id='current-admission', createdAt=1, isSeeded=False, delegationDepth=0)
    message = dict(id='message', role='system', source=dict(kind='plugin', plugin='system'), content=[])
    for kind in ('system/message', 'user/message', 'assistant/message', 'tool/result'):
        current = copy.deepcopy(message)
        if kind == 'user/message':
            current.update(role='user', source=dict(kind='user'))
        elif kind == 'assistant/message':
            current.update(role='assistant', source=dict(kind='model', provider='mock', model='mock'))
        elif kind == 'tool/result':
            current.update(role='user', source=dict(kind='tool', callId='call'), content=[dict(type='tool-result', toolCallId='call', content=[])])
        mutations = [current]
        for key in ('id', 'role', 'source', 'content'):
            missing = copy.deepcopy(current);del missing[key];mutations.append(missing)
            for value in (None, False, 0, '', {}, []):
                mutations.append(dict(copy.deepcopy(current), **{key:value}))
        for value in mutations:
            data = value if kind == 'user/message' else dict(turn=1, step=1, message=value, **({'stream':[]} if kind == 'assistant/message' else {}))
            event = dict(type=kind, seq=0, time=1, data=data, surfaceOp='append')
            add('currentArtifact', artifact=dict(header=header, inheritedEventCount=0, events=[event]))
    for key in ('version', 'id', 'createdAt', 'cwd', 'parentSession', 'isSeeded', 'origin', 'delegationDepth', 'agentPreset', 'seedLength'):
        for value in (None, False, True, -1, 0, '', [], {}, {'$scalar':'-0'}):
            add('currentHeader', header=dict(header, **{key:value}))
    for value in (False, True, None, -1, {'$scalar':'-0'}, 1.5, 2):
        add('currentArtifact', artifact=dict(header=header, inheritedEventCount=value, events=[]))
    output = ROOT/'scripts/oracles/session_current_cases.json'
    output.write_text(json.dumps(list(cases.values()), separators=(',', ':'), ensure_ascii=True)+'\n', encoding='utf-8')
    print(len(cases))


if __name__ == '__main__':
    main()
