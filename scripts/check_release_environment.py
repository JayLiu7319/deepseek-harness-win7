"""Targeted cold-runner checks; retain closed fixtures, never publish a release."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_release import retain_regression_workspace, release_environment
from scripts.package_release_diagnostics import print_summary

NODES = ['tests/test_reference_preparation.py', 'tests/test_frontend_import.py', 'tests/test_release_ci_environment.py',
         'tests/1to1/cordis/test_utils_cosmokit_parity.py', 'tests/test_windows_acl_runner.py',
         'tests/test_windows_confined_console.py', 'tests/test_local_sandbox_provider.py', 'tests/test_pwsh_executor.py',
         'tests/test_canonical_pwsh_tool.py', 'tests/test_deepseek_image_journey.py',
         'tests/test_process_artifact_retention.py::test_actual_gate_teardown_prunes_finished_test_before_next_test',
         'tests/test_current_release_gate.py::test_node_setup_runs_each_locked_workspace_without_prefix_root_ambiguity',
         'tests/test_current_release_gate.py::test_node_setup_refuses_missing_package_manager',
         'tests/test_current_release_gate.py::test_extracted_physical_tree_is_required_and_cannot_hide_survivors[missing]',
         'tests/test_goose_project.py::test_repair_exhaustion_retains_evidence_for_arbitration',
         'tests/test_native_web_browser.py::test_browser_extension_isolation_preserves_application_error_observation']
NODES += ['tests/test_' + name + '_consumers.py' for name in ('agent_dependencies', 'ask_user', 'subagent_model',
          'deepseek_capture', 'deepseek_error', 'fs_values', 'message_values', 'sdk_profile', 'tool_durable',
          'tool_errors', 'unicode_carrier', 'win32_stat')]


def main():
    output = Path(sys.argv[1]).resolve()
    output.relative_to((ROOT / '.goose/out').resolve())
    assert output.is_dir() and not (output / 'pytest.xml').exists()
    parent = Path(tempfile.gettempdir()).resolve()
    try:
        parent.relative_to(ROOT)
    except ValueError:
        pass
    else:
        raise ValueError('Targeted execution TEMP must be outside checkout')
    if os.stat(parent).st_dev != os.stat(output).st_dev:
        raise ValueError('Targeted execution TEMP must be on output volume')
    workspace = Path(tempfile.mkdtemp(prefix='g-', dir=str(parent))).resolve()
    retained = output / 'pytest-workspace'
    assert not retained.exists()
    mapping = dict(format='dsh-release-workspace@2', temporary_parent=str(parent),
                   execution_path=str(workspace), retained_path=str(retained),
                   scope='Fresh owned short external targeted workspace, atomically retained after physical process exit')
    (output / 'pytest-workspace-mapping.json').write_text(json.dumps(mapping, indent=2)+'\n', encoding='utf-8')
    environment = release_environment(os.environ['DSH_TEST_CHROMIUM'])
    environment['DSH_RELEASE_PYTEST_OUTPUT'] = str(output)
    command = [sys.executable, '-m', 'pytest'] + NODES + ['-ra', '--junitxml=' + str(output / 'pytest.xml'), '--basetemp=' + str(workspace)]
    started = time.monotonic()
    try:
        with (output / 'pytest.log').open('xb') as log:
            completed = subprocess.run(command, cwd=str(ROOT), env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    finally:
        if workspace.exists():
            retain_regression_workspace(workspace, retained)
    result = dict(command=command, physicalExit=completed.returncode, seconds=time.monotonic()-started,
                  scope='Targeted environment/provider/consumer checks only; no Portable build or complete release qualification')
    (output / 'environment-result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print_summary(output)
    print(json.dumps(result), flush=True)
    return completed.returncode


if __name__ == '__main__':
    sys.exit(main())
