"""Candidate-only paired checks; never promotes the active migration baseline."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PIN = 'a66e4702047846cdaa10c66c9d3df3951f5ea70d'


def source_inputs(source):
    tracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '-z']).decode('utf-8').rstrip('\0').split('\0')
    paths = set(tracked)
    for manifest in tracked:
        if Path(manifest).name == 'package.json':
            library = (source / manifest).parent / 'lib'
            if library.is_dir():
                paths.update(path.relative_to(source).as_posix() for path in library.rglob('*')
                             if path.is_file() and 'node_modules' not in path.relative_to(library).parts)
    paths.add('.dsh-build/client-build-environment.json')
    return {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in sorted(paths)}


async def native(inputs):
    from dsh.cordis.context import Context
    from dsh.context.file_reference import active_at_token, format_file_mention
    from dsh.context.file_reference_local.search import WorkspaceFileSearch
    from dsh.core.session import SessionStore, SessionSeq, SessionLogOffset
    from dsh.core.session.json import UNDEFINED
    from dsh.core.system_prompt import SystemPrompt
    from dsh.session.projections import SessionProjectionRegistry
    from dsh.session.turn_outline import TURN_OUTLINE_DEFINITION
    rows = dict(grammar=[], mentions=[], searches=[], positions=[], outline=[], changes=[], orders={})
    for row in inputs['tokens']:
        token = active_at_token(row['line'], row['cursor'])
        rows['grammar'].append(token.to_dict() if token else None)
    rows['mentions'] = [format_file_mention(row['candidate'], row['quote']) for row in inputs['mentions']]
    search = WorkspaceFileSearch(inputs['workspace'])
    try:
        for query in inputs['queries']:
            rows['searches'].append(await search.list(query))
    finally:
        search.dispose()
        await search.drain()
    rows['searchLimits'] = []
    for config in inputs['searchConfigs']:
        try:
            configured = WorkspaceFileSearch(inputs['workspace'], config)
            try:
                rows['searchLimits'].append(dict(accepted=True, candidates=await configured.list('py')))
            finally:
                configured.dispose()
                await configured.drain()
        except ValueError as error:
            rows['searchLimits'].append(dict(accepted=False, error=str(error)))
    for brand in (SessionSeq, SessionLogOffset):
        for token in inputs['positions']:
            value = -0.0 if token == '-0' else json.loads(token)
            row = dict(name=brand.__name__, token=token)
            try:
                row['value'] = brand(value)
            except TypeError as error:
                row['error'] = str(error)
            rows['positions'].append(row)
    ctx = Context()
    try:
        await ctx.plugin(SessionStore)
        await ctx.plugin(SessionProjectionRegistry)
        await ctx.plugin(SystemPrompt)
        registry = ctx.get('sessionProjections')
        registry.register(TURN_OUTLINE_DEFINITION)
        registry.onChanged(lambda _s, _k, value, seq: rows['changes'].append(dict(seq=seq, value=value)))
        session = ctx.get('sessions').create('paired-outline')
        for event in inputs['events']:
            session.append(event['type'], event['data'], surface_op=event.get('surfaceOp'))
            rows['outline'].append(registry.snapshot(session))
        first, subset = session.snapshotEvents(), session.snapshotEvents(0, 1)
        rows['indexed'] = dict(cached=first is session.snapshotEvents(), first=session.eventAt(0),
            absent=session.eventAt(session.seq) is UNDEFINED, range=session.snapshotEvents(1, 3))
        try:
            first.append({})
            rows['indexed']['frozen'] = False
        except TypeError:
            rows['indexed']['frozen'] = True
        session.append('probe/mark', {})
        rows['indexed']['stable'] = len(first) == len(inputs['events']) and len(subset) == 1
        prompt = ctx.get('systemPrompt')
        rows['orders'].update((name, prompt.getSectionOrder(name)) for name in inputs['sectionNames'])
        rows['orders'].update((name, prompt.getContextOrder(name)) for name in inputs['contextNames'])
        rows['checkpoint'] = registry.checkpoint(session)
    finally:
        await ctx.fiber.dispose()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    source, output = options.source_root.resolve(), options.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='runner-error', pin=PIN, scope='rc1 candidate capability checks; no baseline or release promotion')
    try:
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], encoding='utf-8').strip()
        if actual != PIN:
            raise ValueError('Source differs from the pinned rc1 candidate')
        workspace = output / 'workspace'
        for directory in ('src', 'lib', 'dist', '.git', '.venv', '..source', 'space dir'):
            (workspace / directory).mkdir(parents=True)
        for filename in ('src/中文 name.py', 'src/alpha.py', 'src/f😀p.py', 'src/fxxp.py', 'lib/alpha.py', 'dist/alpha.py', '.git/a', '.venv/a', '.hidden.py', 'file😀.py', '..source/inside.py', 'space dir/a.txt'):
            (workspace / filename).write_text('PRIVATE_BODY_NOT_A_CANDIDATE', encoding='utf-8')
        from dsh.core.system_prompt import FIRST_PARTY_SECTION_ORDER
        inputs = dict(workspace=str(workspace), clock=1770000000000,
            searchConfigs=[dict(maxResults=1.0, maxEntries=2.0), dict(maxResults=0), dict(maxEntries=True),
                dict(maxResults=1.5), dict(excludedDirectories=['nested/path'])],
            queries=['', 'src/', 'src\\', 'py', 'ap', 'fp', '中文', '.hidden', '../', '..source/', 'space dir/', '😀'],
            tokens=[dict(line=text, cursor=cursor) for text, cursor in [
                ('@src', 4), ('mail@example', 12), ('😀 @src tail', 7), ('@"space dir/', 12),
                ('\ufeff@中文', 4), ('x\u0085@a', 4), ('@😀', 2), ('@a', -1)]],
            mentions=[dict(candidate=dict(path=path, kind=kind), quote=quote) for path, kind, quote in [
                ('src', 'directory', False), ('space dir', 'directory', False), ('中文 name.py', 'file', False),
                ('plain.py', 'file', True), ('bad".py', 'file', False), ('a\ufeffb', 'file', False)]],
            positions=['0', '1', '1.0', '9007199254740991', '-0', '-1', '1.5', 'true', 'null', '"0"', 'NaN', 'Infinity', '9007199254740992'],
            sectionNames=list(FIRST_PARTY_SECTION_ORDER), contextNames=['SANDBOX_POLICY', 'APPROVAL_POLICY', 'SUBAGENT_DELEGATION'], events=[])
        def add(kind, data):
            row = dict(type=kind, data=data)
            if kind in ('user/message', 'assistant/message'):
                row['surfaceOp'] = 'append'
            inputs['events'].append(row)
        add('turn/start', dict(turn=1))
        add('user/message', dict(source=dict(kind='plugin', plugin='fixture'), content=[dict(type='text', text='not human')]))
        add('user/message', dict(source=dict(kind='user'), content=[dict(type='text', text='😀' * 25)]))
        add('user/message', dict(source=dict(kind='user'), content=[dict(type='text', text='steer')]))
        for text in ('draft', '  final\n reply\ufeff '):
            add('assistant/message', dict(message=dict(role='assistant', content=[dict(type='text', text=text)])))
        add('turn/end', dict(turn=1))
        add('turn/start', dict(turn=1))
        add('turn/start', dict(turn=2))
        add('user/message', dict(source=dict(kind='user'), content=[dict(type='text', text=' ' * 10000)]))
        add('turn/end', dict(turn=2))
        input_path = output / 'inputs.json'
        input_path.write_text(json.dumps(inputs, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
        environment = dict(os.environ, TSX_TSCONFIG_PATH=str(source / 'tsconfig.json'))
        frozen = source_inputs(source)
        (output / 'source-inputs.json').write_text(json.dumps(frozen, indent=2) + '\n', encoding='utf-8')
        command = ['node', '--import', (source / 'node_modules/tsx/dist/esm/index.mjs').as_uri(),
            str(ROOT / 'scripts/oracles/rc1_capabilities.mts'), str(source), str(input_path), str(output / 'source.json')]
        run = subprocess.run(command, cwd=str(source), env=environment, capture_output=True, timeout=60)
        (output / 'source.log').write_bytes(run.stdout + run.stderr)
        report['command'], report['exit_code'] = command, run.returncode
        if run.returncode:
            raise RuntimeError('Source observer failed; see source.log')
        source_rows = json.loads((output / 'source.json').read_text(encoding='utf-8'))
        if source_inputs(source) != frozen:
            raise ValueError('Source or compiled library inputs changed during observation')
        expected_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
        if source_rows['pin'] != PIN or source_rows['inputSha256'] != expected_hash:
            raise ValueError('Source identity or input digest differs')
        # Freeze the wall clock solely for paired event-envelope observations.
        import time
        clock = time.time
        time.time = lambda: inputs['clock'] / 1000
        try:
            native_rows = asyncio.run(native(inputs))
        finally:
            time.time = clock
        (output / 'native.json').write_text(json.dumps(native_rows, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
        modules = {}
        for module in list(sys.modules.values()):
            filename = getattr(module, '__file__', None)
            if not filename:
                continue
            path = Path(filename).resolve()
            if path.is_file() and ROOT / 'dsh' in path.parents:
                modules[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        report['native_runtime'] = dict(python=sys.version, executable=sys.executable, modules=modules)
        report['source_inputs_sha256'] = hashlib.sha256((output / 'source-inputs.json').read_bytes()).hexdigest()
        report['input_sha256'] = expected_hash
        report['cases'] = [dict(name=name, matched=value == native_rows.get(name)) for name, value in source_rows['observations'].items()]
        report['status'] = 'matched' if all(row['matched'] for row in report['cases']) else 'different'
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status', 'pin', 'cases', 'error') if key in report}, ensure_ascii=True))
    return {'matched': 0, 'different': 1, 'runner-error': 2}[report['status']]


if __name__ == '__main__':
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
