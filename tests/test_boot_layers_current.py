"""Home-layer admission plus real inserted local plugin consumers."""
import json
from pathlib import Path

import pytest

from dsh.boot.app_boot import (
    LaunchEnvironmentSnapshot, boot, load_optional_patches, load_overlay_patches,
)
from scripts.oracles.boot_layers_current_python import execute
from scripts.session_format_oracle import json_equal


CASES = json.loads((Path(__file__).parents[1] / 'scripts/oracles/boot_layers_current_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['case'])
def test_current_pair(case):
    assert json_equal(execute(case), case['expected'])


def test_boot_snapshot_is_owned_and_case_folded():
    layers = [{'source': 'user-env', 'values': {'http_proxy': 'http://one'}, 'path': 'home/.env'}]
    snapshot = LaunchEnvironmentSnapshot(layers)
    layers[0]['values']['http_proxy'] = 'http://two'
    snapshot.layers[0]['values']['http_proxy'] = 'http://three'
    assert snapshot.get('http_proxy')['value'] == 'http://one'
    import sys
    if sys.platform == 'win32':
        assert snapshot.get('HTTP_PROXY') == snapshot.get('http_proxy')
    assert snapshot.getFrom('http_proxy', ['process']) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('load', [load_optional_patches, load_overlay_patches])
async def test_absolute_insert_loads_actual_plugin(tmp_path, load):
    plugin = tmp_path / 'absolute #100% 中文.py'
    plugin.write_text('def apply(ctx, config):\n    ctx.provide("absolutePatchLoaded", config["value"])\n', encoding='utf-8')
    patch = tmp_path / 'extra.yml'
    patch.write_text(json.dumps([{'insert': [{'id': 'absolute', 'name': str(plugin), 'config': {'value': 'actual'}}]}]), encoding='utf-8')
    patches = load('dsh', str(patch))
    assert patches[0]['insert'][0]['name'] == plugin.as_uri()
    config = tmp_path / 'cordis.yml'
    config.write_text('[]\n', encoding='utf-8')
    ctx = await boot('dsh', str(config), patches)
    try:
        assert ctx.get('absolutePatchLoaded') == 'actual'
    finally:
        await ctx.fiber.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('load', [load_optional_patches, load_overlay_patches])
@pytest.mark.parametrize('relative', [False, True])
async def test_native_python_class_export_is_anchored_separately_from_path(tmp_path, load, relative):
    plugin = tmp_path / 'class #100% 中文.py'
    plugin.write_text('from dsh.cordis.plugin import Plugin\nclass Actual(Plugin):\n'
                      '    def apply(self, ctx):\n        ctx.provide("classExportLoaded", True)\n', encoding='utf-8')
    specifier = ('./' + plugin.name if relative else str(plugin)) + ':Actual'
    patch = tmp_path / 'extra.yml'
    patch.write_text(json.dumps([dict(insert=[dict(id='actual', name=specifier)])]), encoding='utf-8')
    patches = load('dsh', str(patch))
    assert patches[0]['insert'][0]['name'] == str(plugin) + ':Actual'
    config = tmp_path / 'cordis.yml'
    config.write_text('[]\n', encoding='utf-8')
    ctx = await boot('dsh', str(config), patches)
    try:
        assert ctx.get('classExportLoaded') is True
    finally:
        await ctx.fiber.dispose()
