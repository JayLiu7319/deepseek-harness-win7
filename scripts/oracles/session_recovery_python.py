import asyncio
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dsh.session.jsonl_backend_current import CurrentJsonlSessionPersistence

async def observe():
    rows = []
    fixtures = json.loads(Path(__file__).with_name('session-recovery-fixtures.json').read_text(encoding='utf-8'))
    for fixture in fixtures:
        with tempfile.TemporaryDirectory() as root:
            p = CurrentJsonlSessionPersistence(root, compression='none')
            sid = fixture['mode']
            path = Path(root) / '_no-cwd' / sid / 'session.jsonl'
            path.parent.mkdir(parents=True, exist_ok=True)
            header = dict(type='session', id=sid, version=0, createdAt=1, delegationDepth=0)
            raw = ('\n'.join(json.dumps(e) for e in [header] + fixture['events']) + '\n' + fixture['tail']).encode('utf-8')
            path.write_bytes(raw)
            reader = await p.open(sid, 'read')
            inspected = await reader.read()
            before = await reader.read(1)
            await reader.close()
            untouched = path.read_bytes() == raw
            writer = await p.open(sid, 'write')
            loaded = await writer.read()
            await writer.close()
            reopened = await p.open(sid, 'read')
            again = await reopened.read()
            after = await reopened.read(0)
            await reopened.close()
            rows.append(dict(mode=sid, inspected=inspected['events'], before=before['events'],
                untouched=untouched, loaded=loaded['events'], again=again['events'], after=after['events']))
    return rows

if __name__ == '__main__':
    Path(sys.argv[1]).write_text(json.dumps(asyncio.run(observe()), indent=2)+'\n', encoding='utf-8')
