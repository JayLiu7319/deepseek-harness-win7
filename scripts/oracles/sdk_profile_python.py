import hashlib
import json
import os
from pathlib import Path
import sys


selected_root = Path(os.environ['DSH_SDK_NATIVE_ROOT']).resolve()
sys.path.insert(0, str(selected_root))
import apps.cli.main as cli

original_run_profile = cli.run_profile


async def observed_profile(options):
    result = await original_run_profile(dict(options, wait_for_exit=False))
    def observed(info):
        frame = info['frame']
        if frame['type'] != 'chunk' or frame['chunk']['type'] != 'text-delta' or frame['chunk'].get('text') != 'SDK_PENDING':
            return
        path = Path(os.environ['DSH_SDK_LIVE_BARRIER'])
        temporary = path.with_name(path.name+'.tmp')
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(dict(sessionId=info['agent'].session.id,frame=frame),stream)
        os.replace(str(temporary),str(path))
    result['ctx'].on('agent/assistant-stream', observed)
    await result['shutdown'].wait()
    return result


cli.run_profile = observed_profile


try:
    cli.main()
finally:
    modules = {}
    for name, module in sorted(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if filename and (name == 'dsh' or name.startswith('dsh.') or name == 'apps' or name.startswith('apps.')):
            path = Path(filename).resolve()
            modules[path.relative_to(selected_root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    with Path(os.environ['DSH_SDK_RUNTIME_OUTPUT']).open('x', encoding='utf-8') as stream:
        json.dump(dict(root=str(selected_root), executable=sys.executable, python=sys.version, modules=modules), stream, indent=2)
        stream.write('\n')
