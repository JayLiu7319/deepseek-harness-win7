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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    output = args.output_dir.resolve()
    output.relative_to(ROOT / '.goose/out')
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='runner-error', target_upstream=TARGET,
        scope='Synthetic format planner/catalog contracts only, not released codecs or persistence acceptance',
        commands=[], cases=[])
    def git(*args):
        return subprocess.check_output(['git', '-C', str(source)] + list(args), encoding='utf-8', timeout=20).strip()
    try:
        if git('rev-parse', 'HEAD') != TARGET or git('status', '--porcelain'):
            raise ValueError('Unchanged rc.3 Source required')
        cases = json.loads(CORPUS.read_text(encoding='utf-8'))
        names = [case['case'] for case in cases]
        if not names or len(names) != len(set(names)):
            raise ValueError('Empty or duplicate corpus cases')
        report['inputs'] = {str(path.relative_to(ROOT)).replace('\\', '/'):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [CORPUS, ROOT/'scripts/oracles/session_format_python.py', ROOT/'scripts/oracles/session_format_source.mts']}
        commands = [
            ['node', str(source/'node_modules/tsx/dist/cli.mjs'), '--tsconfig', str(source/'tsconfig.json'),
             str(ROOT/'scripts/oracles/session_format_source.mts'), str(source), str(CORPUS), str(output/'source.json')],
            [sys.executable, str(ROOT/'scripts/oracles/session_format_python.py'), str(CORPUS), str(output/'native.json')],
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
            if [row['case'] for row in rows] != names:
                raise ValueError('Missing, duplicated or unexpected observations')
            observations.append(rows)
        for source_row, native_row in zip(*observations):
            report['cases'].append(dict(case=source_row['case'], status='matched' if source_row == native_row else 'different',
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
