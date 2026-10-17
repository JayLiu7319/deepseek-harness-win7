"""Own a development Desktop test through shutdown; never detach its log pipes."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--electron', type=Path, default=ROOT / '.goose/tools/electron-22.3.27-win32-x64/runtime/electron.exe')
    parser.add_argument('--limited-shell', action='store_true')
    parser.add_argument('--root', type=Path, default=ROOT,
                        help='Python-host root; run this runner with that root\'s Python for Portable checks')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = dict(status='running', started=time.time())
    command = [str(args.electron.resolve()), str(ROOT / 'apps/desktop'), '--root', str(args.root.resolve()),
               '--python', sys.executable, '--home', str(output / 'home'),
               '--test-output', str(output / 'observations')]
    if args.limited_shell:
        command.extend(['--test-limited-shell', 'true'])
    report['command'] = command
    env = dict(os.environ, DSH_TELEMETRY_DISABLED='1', PYTHONDONTWRITEBYTECODE='1')
    env.pop('ELECTRON_RUN_AS_NODE', None)
    child = None
    try:
        # An owned regular file remains writable after the initiating shell exits.
        with (output / 'desktop.log').open('wb') as log:
            child = subprocess.Popen(command, cwd=str(ROOT), env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT)
            report['pid'] = child.pid
            (output / 'runner.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            report['exitCode'] = child.wait(timeout=300)
        observed = json.loads((output / 'observations/report.json').read_text(encoding='utf-8'))
        if report['exitCode'] != 0 or observed['status'] != 'qualified':
            raise RuntimeError('Desktop smoke rejected; see observations and desktop.log')
        report['status'] = 'qualified'
    except Exception as error:
        report.update(status='rejected', failure=repr(error))
    finally:
        if child is not None and child.poll() is None:
            # Popen still owns this live PID; kill its exact process tree only.
            cleanup = subprocess.run(['taskkill.exe', '/PID', str(child.pid), '/T', '/F'],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            report['cleanup'] = dict(exitCode=cleanup.returncode, output=cleanup.stdout.decode('utf-8', 'replace'))
            child.wait(timeout=15)
        report['elapsedSeconds'] = round(time.time() - report['started'], 3)
        (output / 'runner.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['status'] == 'qualified' else 1


if __name__ == '__main__':
    sys.exit(main())
