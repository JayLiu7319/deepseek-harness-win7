"""JSON-line actor for real native cross-process Session write-lock tests."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dsh.session.lease import SessionWriteLease


async def main():
    held = {}
    print(json.dumps(dict(ready=True)), flush=True)
    for line in sys.stdin:
        try:
            command = json.loads(line)
            if command['action'] == 'acquire':
                held[command['slot']] = await SessionWriteLease.acquire(command['directory'], command['id'])
            elif command['action'] == 'release':
                await held[command['slot']].release()
            elif command['action'] == 'exit':
                break
            else:
                raise ValueError('Unknown actor command')
            response = dict(outcome='value')
        except Exception as error:
            response = dict(outcome='error', name=getattr(error, 'name', type(error).__name__), message=str(error))
        print(json.dumps(response), flush=True)
    for lease in held.values():
        await lease.release()


if __name__ == '__main__':
    asyncio.run(main())
