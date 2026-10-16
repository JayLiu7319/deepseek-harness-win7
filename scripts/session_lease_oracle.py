"""Exercise real cross-process exclusion and crash release, optionally across runtimes."""
import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'a4c74a91e06b00fe0b0937bde982170c526cc842'


class LeaseActor:
    def __init__(self, command, log_path):
        self.log = open(str(log_path), 'x', encoding='utf-8')
        self.process = subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, encoding='utf-8', bufsize=1)
        self.output = queue.Queue()
        def read():
            for line in self.process.stdout:
                self.output.put(line)
            self.output.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            if self.response() != dict(ready=True):
                raise RuntimeError('Unexpected lease actor readiness')
        except BaseException:
            self.close(kill=True)
            raise

    def response(self):
        line = self.output.get(timeout=20)
        if line is None:
            raise RuntimeError('Lease actor exited before replying')
        return json.loads(line)

    def send(self, **command):
        self.process.stdin.write(json.dumps(command, ensure_ascii=True)+'\n')
        self.process.stdin.flush()
        return self.response()

    def close(self, kill=False):
        try:
            if self.process.poll() is None:
                if kill:
                    self.process.kill()
                else:
                    self.process.stdin.write('{"action":"exit"}\n')
                    self.process.stdin.flush()
                self.process.wait(timeout=10)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=10)
            self.process.stdin.close()
            self.reader.join(timeout=2)
            self.process.stdout.close()
            self.log.close()


def run_scenario(first_command, second_command, output, crash=False):
    output.mkdir()
    first, second = None, None
    observations = []
    directory = output/'session-中文'
    try:
        first = LeaseActor(first_command, output/'first.stderr.log')
        second = LeaseActor(second_command, output/'second.stderr.log')
        def invoke(actor, label, action, slot='shared', path=directory, identity='lease-session'):
            response = actor.send(action=action, slot=slot, directory=str(path.resolve()), id=identity)
            observations.append(dict(actor=label, action=action, response=response))
            expected = dict(outcome='error', name='SessionAlreadyOwnedError', message='session "lease-session" is already owned by an active write handle') if label == 'contender' else dict(outcome='value')
            if response != expected:
                raise AssertionError('Unexpected lease observation: '+str(observations[-1]))
        invoke(first, 'holder', 'acquire')
        invoke(second, 'contender', 'acquire')
        invoke(second, 'independent', 'acquire', slot='other', path=output/'other', identity='other')
        invoke(second, 'independent', 'release', slot='other')
        # Readers and directory removal remain usable on Windows while held.
        (directory/'observation.txt').write_text('readable', encoding='utf-8')
        assert (directory/'observation.txt').read_text(encoding='utf-8') == 'readable'
        (directory/'observation.txt').unlink()
        if os.name == 'nt':
            directory.rmdir()
            directory.mkdir()
            invoke(second, 'contender', 'acquire')
            invoke(second, 'contender', 'acquire', path=Path(str(directory).upper()))
        if crash:
            first.close(kill=True)
            first = None
        else:
            invoke(first, 'holder', 'release')
            invoke(first, 'holder', 'release')
        invoke(second, 'successor', 'acquire')
        invoke(second, 'successor', 'release')
        return observations
    finally:
        if first is not None:
            first.close()
        if second is not None:
            second.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output_dir.resolve()
    output.relative_to(ROOT/'.goose/out')
    output.mkdir(parents=True, exist_ok=False)
    def git(*arguments):
        return subprocess.check_output(['git','-C',str(source)]+list(arguments), encoding='utf-8', timeout=20).strip()
    if git('rev-parse','HEAD') != TARGET or git('status','--porcelain'):
        raise ValueError('Clean rc.3 Source required')
    native = [sys.executable, str(ROOT/'scripts/oracles/session_lease_worker.py')]
    official = ['node', str(source/'node_modules/tsx/dist/cli.mjs'), '--tsconfig', str(source/'tsconfig.json'),
        str(ROOT/'scripts/oracles/session_lease_worker.mts'), str(source)]
    report = dict(target_upstream=TARGET, platform=sys.platform, scenarios=[], status='failed')
    start = time.monotonic()
    try:
        for first, second, name in ((native,native,'native-native'),(official,official,'source-source'),(native,official,'native-source'),(official,native,'source-native')):
            for crash in (False, True):
                observations = run_scenario(first, second, output/(name+('-crash' if crash else '-close')), crash)
                report['scenarios'].append(dict(actors=name, crash=crash, commands=[first,second], observations=observations))
        if git('rev-parse','HEAD') != TARGET or git('status','--porcelain'):
            raise ValueError('Source changed during lease observation')
        report['status'] = 'passed'
    except Exception as error:
        report['error'] = str(error)
    report['elapsed_seconds'] = time.monotonic()-start
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['status'])
    return 0 if report['status']=='passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
