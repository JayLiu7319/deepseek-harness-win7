"""Electron's real Node 16 survives terminal closure without hiding other errors."""
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_actual_closed_parent_pipes():
    electron = Path(os.environ.get('DSH_DESKTOP_ELECTRON', str(
        ROOT / '.goose/tools/electron-22.3.27-win32-x64/runtime/electron.exe')))
    if not electron.is_file():
        pytest.skip('Pinned Electron 22 runtime required for actual closed Windows pipes')
    result = subprocess.run([str(electron), str(ROOT / 'scripts/oracles/desktop_stdio_current.cjs'),
                             str(electron)], env=dict(os.environ, ELECTRON_RUN_AS_NODE='1'),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8', timeout=20)
    assert result.returncode == 0, result.stdout
    report = json.loads(result.stdout)
    assert report['status'] == 'qualified'
    assert {row['stream'] for row in report['observations'] if row['phase'] == 'pipe-error'} == {'stdout', 'stderr'}
