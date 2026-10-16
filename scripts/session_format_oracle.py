"""Compare explicit rc.3 Source/native pure-format contracts without moving the active pin."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'a4c74a91e06b00fe0b0937bde982170c526cc842'
CORPUS = ROOT / 'scripts/oracles/session_format_cases.json'


def json_equal(left, right):
    """JSON numbers share one domain; booleans must never compare equal to 0/1."""
    if type(left) in (int, float) and type(right) in (int, float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(json_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(json_equal(a, b) for a, b in zip(left, right))
    return left == right


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, default=CORPUS)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    corpus = args.corpus.resolve()
    output = args.output_dir.resolve()
    output.relative_to(ROOT / '.goose/out')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='runner-error', target_upstream=TARGET,
        scope='Explicit corpus of format, physical codec, released logical migration and Assistant stream contracts; not production persistence or release acceptance',
        commands=[], cases=[])
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source)] + list(args), encoding='utf-8', timeout=20).strip()
    try:
        if git('rev-parse', 'HEAD') != TARGET or git('status', '--porcelain'):
            raise ValueError('Unchanged rc.3 Source required')
        cases = json.loads(corpus.read_text(encoding='utf-8'))
        names = [case['case'] for case in cases]
        if not names or len(names) != len(set(names)):
            raise ValueError('Empty or duplicate corpus cases')
        inputs = [corpus, ROOT/'scripts/session_format_oracle.py',
            ROOT/'scripts/oracles/session_format_python.py', ROOT/'scripts/oracles/session_format_source.mts']
        if any(case.get('kind') == 'session-agents-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_agents_current_python.py', ROOT/'scripts/oracles/session_agents_current_source.mts'])
        if any(case.get('kind') == 'session-list-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_list_current_python.py', ROOT/'scripts/oracles/session_list_current_source.mts'])
        if any(case.get('kind') == 'file-upload-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/file_upload_current_python.py', ROOT/'scripts/oracles/file_upload_current_source.mts'])
        if any(case.get('kind') == 'llm-files-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/llm_files_current_python.py', ROOT/'scripts/oracles/llm_files_current_source.mts'])
        if any(case.get('kind') == 'session-media-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_media_current_python.py', ROOT/'scripts/oracles/session_media_current_source.mts'])
        if any(case.get('kind') == 'attachment-images-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/attachment_images_current_python.py', ROOT/'scripts/oracles/attachment_images_current_source.mts'])
        if any(case.get('kind') == 'attachment-files-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/attachment_files_current_python.py', ROOT/'scripts/oracles/attachment_files_current_source.mts'])
        if any(case.get('kind') == 'generation' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_generation_python.py', ROOT/'scripts/oracles/session_generation_source.mts'])
        if any(case.get('kind') == 'session-runtime' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_runtime_python.py', ROOT/'scripts/oracles/session_runtime_source.mts'])
        if any(case.get('kind') in ('storage-contract','storage-handle') for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_storage_current_python.py', ROOT/'scripts/oracles/session_storage_source.mts'])
        if any(case.get('kind') == 'storage-backend' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_backend_current_python.py', ROOT/'scripts/oracles/session_backend_current_source.mts',ROOT/'scripts/oracles/session_storage_current_python.py'])
        if any(case.get('kind') == 'query-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/session_query_current_python.py',ROOT/'scripts/oracles/session_query_current_source.mts'])
        if any(case.get('kind') == 'loop-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/agent_loop_current_python.py',ROOT/'scripts/oracles/agent_loop_current_source.mts'])
            if any(case.get('operation') == 'compaction' for case in cases):
                inputs.extend([ROOT/'scripts/oracles/compaction_current_python.py',ROOT/'scripts/oracles/compaction_current_source.mts'])
            if any(case.get('operation') == 'meter-units' for case in cases):
                inputs.extend([ROOT/'scripts/oracles/token_meter_units_current_python.py',ROOT/'scripts/oracles/token_meter_units_current_source.mts'])
            if any(case.get('operation') == 'goal-units' for case in cases):
                inputs.extend([ROOT/'scripts/oracles/goal_units_current_python.py',ROOT/'scripts/oracles/goal_units_current_source.mts'])
            if any(case.get('operation') == 'external-units' for case in cases):
                inputs.extend([ROOT/'scripts/oracles/external_units_current_python.py',ROOT/'scripts/oracles/external_units_current_source.mts'])
            if any(case.get('operation') in ('catalog','continuation-messages','subagent-inbox') for case in cases):
                inputs.extend([ROOT/'scripts/oracles/subagent_units_current_python.py',ROOT/'scripts/oracles/subagent_units_current_source.mts'])
        if any(case.get('kind') == 'machine-current' for case in cases):
            inputs.extend([ROOT/'scripts/oracles/agent_machine_current_python.py',ROOT/'scripts/oracles/agent_machine_current_source.mts'])
        report['inputs'] = {str(path.relative_to(ROOT)).replace('\\', '/'):hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs}
        commands = [
            ['node', str(source/'node_modules/tsx/dist/cli.mjs'), '--tsconfig', str(source/'tsconfig.json'),
             str(ROOT/'scripts/oracles/session_format_source.mts'), str(source), str(corpus), str(output/'source.json')],
            [sys.executable, str(ROOT/'scripts/oracles/session_format_python.py'), str(corpus), str(output/'native.json')],
        ]
        observations = []
        for index, command in enumerate(commands):
            start = time.monotonic()
            with (output/('%s.log' % index)).open('x', encoding='utf-8') as log:
                run = subprocess.run(command, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, timeout=60)
            report['commands'].append(dict(command=command, exit_code=run.returncode, elapsed_seconds=time.monotonic()-start))
            if run.returncode:
                raise RuntimeError('Runner %s failed with %s' % (index, run.returncode))
            rows = json.loads((output/('source.json' if index == 0 else 'native.json')).read_text(encoding='utf-8'))
            for case,row in zip(cases,rows):
                if case.get('kind') in ('query-current','loop-current','machine-current') and row.get('outcome')!='value':
                    raise RuntimeError('Journey failed before actions: '+case['case']+': '+str(row))
            if [row['case'] for row in rows] != names:
                raise ValueError('Missing, duplicated or unexpected observations')
            observations.append(rows)
        for source_row, native_row in zip(*observations):
            report['cases'].append(dict(case=source_row['case'], status='matched' if json_equal(source_row, native_row) else 'different',
                source=source_row, native=native_row))
        report['status'] = 'matched' if all(row['status'] == 'matched' for row in report['cases']) else 'different'
        if git('rev-parse', 'HEAD') != TARGET or git('status', '--porcelain'):
            raise ValueError('Source changed during observation')
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        report.update(status='runner-error', error=str(error))
    with (output/'report.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(report['status'])
    return {'matched':0, 'different':1, 'runner-error':2}[report['status']]


if __name__ == '__main__':
    raise SystemExit(main())
