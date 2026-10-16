"""Candidate discovery must not inherit old pins or turn declarations into parity."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import candidate_inventory as candidate


def commit(root):
    env = dict(os.environ, GIT_AUTHOR_NAME='Candidate fixture', GIT_COMMITTER_NAME='Candidate fixture',
        GIT_AUTHOR_EMAIL='candidate@example.invalid', GIT_COMMITTER_EMAIL='candidate@example.invalid')
    for args in (['add', '.'], ['commit', '-qm', 'fixture']):
        subprocess.run(['git', '-C', str(root)] + args, env=env, check=True, capture_output=True)
    return candidate.git(root, 'rev-parse', 'HEAD').decode().strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True, capture_output=True)
    bodies = {
        'package.json': dict(name='root'),
        'packages/bundle/base/package.json': dict(name='@fixture/base',
            dependencies={'@fixture/consumer': 'workspace:*'}, devDependencies={'@fixture/dev': 'workspace:*'}),
        'packages/core/provider/package.json': dict(name='@fixture/provider'),
        'packages/core/consumer/package.json': dict(name='@fixture/consumer', dependencies={'@fixture/provider': 'workspace:*'}),
        'packages/support/dev/package.json': dict(name='@fixture/dev'),
        'packages/old/package.json': dict(name='@fixture/removed'),
    }
    for name, body in bodies.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body)+'\n', encoding='utf-8')
    profile = root / 'packages/boot/app-boot/src/profile.ts'
    profile.parent.mkdir(parents=True)
    profile.write_text("export const PROFILE_TEMPLATES: Record<string, ProfileTemplate> = {\n"
        "  web: { bundles: ['@fixture/base'], patchReload: 'live' },\n"
        "  'sdk-minimal': { bundles: ['@fixture/provider'], patchReload: 'startup' },\n}\n", encoding='utf-8')
    (root / 'packages/bundle/base/cordis.patch.yml').write_text(
        "- insert:\n    - id: provider\n      name: '@fixture/provider/invariant'\n      disabled: !!js process.platform !== 'win32'\n", encoding='utf-8')
    (root / 'packages/core/provider/value 中文.txt').write_text('before\n', encoding='utf-8')
    base = commit(root)
    (root / 'packages/old/package.json').unlink()
    (root / 'packages/core/provider/value 中文.txt').write_text('after\n', encoding='utf-8')
    target = commit(root)
    # Discovery reads the target Git tree even with the checkout left at base.
    subprocess.run(['git', '-C', str(root), 'checkout', '--detach', '-q', base], check=True)
    return root, base, target


def test_arbitrary_target_tree_maps_runtime_consumers_without_changing_checkout(repository, tmp_path, monkeypatch):
    from dsh.boot import plugin_registry
    root, base, target = repository
    monkeypatch.setattr(plugin_registry, 'HARNESS_PLUGIN_CLASSES', {'@fixture/provider/invariant': 'fixture:Provider'})
    before = candidate.git(root, 'status', '--porcelain=v1')
    result = candidate.generate(root, base, target, tmp_path)
    assert result['target_upstream'] == target and result['base_upstream'] == base
    assert result['unchanged_checkout'] == base
    assert candidate.git(root, 'rev-parse', 'HEAD').decode().strip() == base
    assert candidate.git(root, 'status', '--porcelain=v1') == before
    assert result['counts']['manifests'] == 5
    assert result['removed_manifests'] == [dict(path='packages/old/package.json', name='@fixture/removed')]
    assert result['profiles']['web']['potential_dependency_closure'] == ['@fixture/base', '@fixture/consumer', '@fixture/provider']
    assert '@fixture/dev' not in result['profiles']['web']['potential_dependency_closure']
    provider = next(r for r in result['manifests'] if r['name'] == '@fixture/provider')
    assert provider['python_loader_entrypoints'] == {'@fixture/provider/invariant': 'fixture:Provider'}
    assert provider['parity'] == 'not-certified-by-inventory'
    assert result['runtime_dependency_impact']['transitive'] == ['packages/bundle/base', 'packages/core/consumer']
    rows = result['declarations']['packages/bundle/base/cordis.patch.yml']
    assert rows['entries'][0]['package'] == '@fixture/provider'
    assert rows['conditions'][0]['line'] == 4
    assert 'never observed activation' in result['profiles']['web']['scope']


def test_newline_blob_request_and_unknown_revision_are_refused(repository):
    root, base, target = repository
    with pytest.raises(ValueError, match='line separator'):
        candidate.blobs(root, target, ['package.json\nHEAD:package.json'])
    for ref in ('--help', 'HEAD\0bad', 'missing-ref'):
        with pytest.raises(ValueError):
            candidate.generate(root, base, ref)


def test_nonliteral_template_cannot_silently_change_profile_roots():
    text = "export const PROFILE_TEMPLATES: Record<string, X> = {\n web: { bundles: compute(), patchReload: 'live' },\n}\n"
    with pytest.raises(ValueError, match='Nonliteral'):
        candidate.target_profiles(text)


def test_lane_audit_uses_actual_config_and_exposes_removed_paths_and_old_pins(tmp_path):
    script = tmp_path / 'scripts/verify_release.py'
    script.parent.mkdir()
    script.write_text("PAIRED_DRIVERS = ('one',)\nPAIRED_DRIVERS = PAIRED_DRIVERS + ('two',)\nOFFICIAL_CONFIGS = ('core',)\nOFFICIAL_CONFIGS += ('web',)\n", encoding='utf-8')
    lanes = candidate.release_lanes(script)
    assert lanes == dict(PAIRED_DRIVERS=['one', 'two'], OFFICIAL_CONFIGS=['core', 'web'])
    for name in ('one', 'two'):
        (script.parent / (name+'_oracle.py')).write_text("PIN = '" + 'a'*40 + "'\n", encoding='utf-8')
    for name in ('core', 'web'):
        path = script.parent / ('oracles/vitest.'+name+'.config.mts')
        path.parent.mkdir(exist_ok=True)
        path.write_text("['reference/packages/old/tests/*.spec.ts']\n", encoding='utf-8')
    audit = candidate.lane_audit(tmp_path, lanes, ['packages/new/tests/one.spec.ts'])
    assert audit['OFFICIAL_CONFIGS'][0]['literal_source_paths'][0]['target_matches'] == 0
    assert audit['PAIRED_DRIVERS'][0]['literal_pins'] == ['a'*40]
    assert audit['OFFICIAL_CONFIGS'][0]['state'] == 'contract-review-required'


def test_candidate_output_is_exclusive_and_protects_active_records(repository, tmp_path):
    root, _, _ = repository
    for path in (root / 'package.json', tmp_path / '.git/record.json', tmp_path / 'migration/baseline.json'):
        with pytest.raises(ValueError):
            candidate.write_report({}, path, root, tmp_path)
    output = tmp_path / 'migration/candidates/new/report.json'
    candidate.write_report({'candidate': True}, output, root, tmp_path)
    with pytest.raises(FileExistsError):
        candidate.write_report({}, output, root, tmp_path)
    assert json.loads(output.read_text(encoding='utf-8')) == {'candidate': True}


def test_cli_invalid_target_produces_no_report(repository, tmp_path):
    root, base, _ = repository
    output = tmp_path / 'no-report.json'
    result = subprocess.run([sys.executable, str(Path(candidate.__file__)), '--repository', str(root),
        '--base', base, '--target', 'missing', '--output', str(output)], capture_output=True, timeout=20)
    assert result.returncode != 0 and not output.exists()
