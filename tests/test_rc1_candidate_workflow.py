"""Candidate discovery stays separate from active records and actual activation."""
import json
from pathlib import Path
import subprocess

import pytest

from scripts import rc1_inventory


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root)] + list(args), encoding='utf-8').strip()


def test_candidate_graph_resolves_package_subpaths_and_excludes_dev_only_edges(tmp_path, monkeypatch):
    from dsh.boot import profile, plugin_registry
    source = tmp_path / 'source'
    source.mkdir()
    git(source, 'init', '-q')
    bodies = {
        'package.json': dict(name='fixture-root'),
        'packages/bundle/base/package.json': dict(name='@fixture/base', dependencies={'@fixture/interface': 'workspace:^'},
            devDependencies={'@fixture/test-only': 'workspace:^'}),
        'packages/core/provider/package.json': dict(name='@fixture/provider'),
        'packages/core/interface/package.json': dict(name='@fixture/interface'),
        'packages/test-support/example/package.json': dict(name='@fixture/test-only'),
    }
    for relative, body in bodies.items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body) + '\n', encoding='utf-8')
    (source / 'packages/bundle/base/cordis.patch.yml').write_text(
        "- insert:\n    - id: fixture\n      name: '@fixture/provider/invariant'\n", encoding='utf-8')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Candidate Fixture', '-c', 'user.email=candidate@example.invalid', 'commit', '-qm', 'fixture')
    monkeypatch.setattr(rc1_inventory, 'PIN', git(source, 'rev-parse', 'HEAD'))
    active_root = tmp_path / 'active'
    (active_root / 'migration/contracts').mkdir(parents=True)
    (active_root / 'migration/baseline.json').write_text('{"accepted_upstream":null}\n', encoding='utf-8')
    (active_root / 'migration/modules.json').write_text(json.dumps(dict(
        target_upstream=rc1_inventory.PIN, manifests=[])) + '\n', encoding='utf-8')
    monkeypatch.setattr(rc1_inventory, 'ROOT', active_root)
    monkeypatch.setattr(profile, 'PROFILE_TEMPLATES', dict(web=dict(bundles=['@fixture/base'])))
    monkeypatch.setattr(plugin_registry, 'HARNESS_PLUGIN_CLASSES', {'@fixture/provider/invariant': 'fixture:Provider'})
    before = git(source, 'status', '--porcelain')
    active = (rc1_inventory.ROOT / 'migration/baseline.json').read_bytes()
    inventory = (rc1_inventory.ROOT / 'migration/modules.json').read_bytes()
    data = rc1_inventory.generate(source)
    assert data['counts']['manifests'] == len(bodies)
    assert data['profiles']['web']['declared_dependency_closure'] == ['@fixture/base', '@fixture/interface', '@fixture/provider']
    provider = next(row for row in data['manifests'] if row['name'] == '@fixture/provider')
    assert provider['python_loader_entrypoints'] == {'@fixture/provider/invariant': 'fixture:Provider'}
    assert provider['python_loader_provider'] is None
    assert provider['parity'] == 'not-certified-by-inventory'
    assert 'never observed activation' in data['profiles']['web']['limitation']
    assert git(source, 'status', '--porcelain') == before
    assert (rc1_inventory.ROOT / 'migration/baseline.json').read_bytes() == active
    assert (rc1_inventory.ROOT / 'migration/modules.json').read_bytes() == inventory
    (source / 'package.json').write_text('{}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='clean pinned'):
        rc1_inventory.generate(source)


def test_candidate_cli_refuses_foreign_source_without_creating_an_inventory(tmp_path):
    source = tmp_path / 'foreign'
    source.mkdir()
    git(source, 'init', '-q')
    (source / 'package.json').write_text('{}\n', encoding='utf-8')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Candidate Fixture', '-c', 'user.email=candidate@example.invalid', 'commit', '-qm', 'foreign')
    output = tmp_path / 'should-not-exist.json'
    import sys
    run = subprocess.run([sys.executable, str(Path(rc1_inventory.__file__)), '--source-root', str(source),
        '--output', str(output)], capture_output=True, timeout=20)
    assert run.returncode != 0
    assert not output.exists()
