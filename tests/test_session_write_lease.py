"""Real kernel exclusion, process death and readers while a writer owns a Session."""
import sys

import pytest

from scripts.session_lease_oracle import ROOT, run_scenario


@pytest.mark.parametrize('crash', [False, True])
def test_native_two_process_lease(tmp_path, crash):
    command = [sys.executable, str(ROOT/'scripts/oracles/session_lease_worker.py')]
    observations = run_scenario(command, command, tmp_path/'run', crash)
    assert observations[-1]['response'] == dict(outcome='value')
