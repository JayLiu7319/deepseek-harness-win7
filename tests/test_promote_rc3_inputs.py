import json
from pathlib import Path
import zipfile
import pytest
import yaml
from scripts import promote_rc3_inputs as tool


def test_wrong_source_is_refused_before_runtime_inputs_are_read(tmp_path, monkeypatch):
    monkeypatch.setattr(tool.subprocess, 'check_output', lambda *args, **kwargs: '0' * 40)
    with pytest.raises(ValueError, match='Unchanged pinned'):
        tool.selected_inputs(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_import_preserves_exact_old_bytes_and_only_applies_declared_product_overlays(tmp_path, monkeypatch):
    minimal='packages/preset/agent-presets/presets/minimal/agent.cordis.yml'
    sdk='packages/bundle/sdk-minimal/cordis.patch.yml'
    metadata='packages/preset/agent-presets/presets/minimal/preset.yml'
    values={minimal:b'- id: persona\n  config:\n    prefix: helpful\n', sdk:b'- insert:\n    - id: original\n',metadata:b'name: minimal\n',
            'apps/cli/package.json':b'{"version":"0.1.5-rc.3"}\n'}
    old=b'# The bare local filesystem shadows the host.\n- id: filesystem\n  config: []\n'
    p=tmp_path/minimal;p.parent.mkdir(parents=True);p.write_bytes(old)
    monkeypatch.setattr(tool,'selected_inputs',lambda source:dict(values))
    report=tool.import_inputs(tmp_path/'source',tmp_path,tmp_path/'.goose/out/import')
    with zipfile.ZipFile(str(tmp_path/'.goose/out/import/previous-runtime-inputs.zip')) as z:
        assert z.read(minimal)==old
    assert (tmp_path/'apps/cli/package.json').read_bytes()==values['apps/cli/package.json']
    assert yaml.safe_load((tmp_path/minimal).read_text(encoding='utf-8'))[-1]['id']=='filesystem'
    assert [row['id'] for row in yaml.safe_load((tmp_path/sdk).read_text(encoding='utf-8'))[0]['insert']]==['original','fs-local','str-replace-editor']
    assert sum(row['product_overlay'] for row in report['files'])==3
    assert json.loads((tmp_path/'.goose/out/import/report.json').read_text(encoding='utf-8'))==report
    tool.validate_runtime_inputs(tmp_path,report,tool.TARGET)
    (tmp_path/'apps/cli/package.json').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Runtime input differs'):
        tool.validate_runtime_inputs(tmp_path,report,tool.TARGET)


def test_output_outside_owned_verification_tree_is_refused(tmp_path,monkeypatch):
    monkeypatch.setattr(tool,'selected_inputs',lambda source:{})
    with pytest.raises(ValueError): tool.import_inputs(tmp_path/'source',tmp_path,tmp_path/'unowned')
    assert not (tmp_path/'unowned').exists()
