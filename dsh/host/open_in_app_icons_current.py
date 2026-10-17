"""rc.3 native icon extraction with bounded commands and owned temp files."""
import json
import os
import tempfile
from pathlib import Path

from dsh.host.open_in_app_resolver_current import (find_desktop_entry, is_file, join,
    output, resolve_internals, spec_for, xdg_data_directories)

EXTRACT_ICON_PS1 = '\n'.join([
    'param([string]$Source, [string]$Target)',
    '$ErrorActionPreference = "Stop"',
    'Add-Type -AssemblyName System.Drawing',
    '$icon = [System.Drawing.Icon]::ExtractAssociatedIcon($Source)',
    'if ($null -eq $icon) { exit 1 }',
    '$bitmap = $icon.ToBitmap()',
    '$bitmap.Save($Target, [System.Drawing.Imaging.ImageFormat]::Png)', ''])
HICOLOR_SIZES = ['512x512', '256x256', '128x128', '64x64', '48x48', '32x32']


async def extract_bundle_icon_png(bundle, timeout_ms, facts):
    resources = join(bundle, 'Contents', 'Resources')
    icon = None
    plist = await output('plutil', ['-convert', 'json', '-o', '-', join(bundle, 'Contents', 'Info.plist')], timeout_ms, facts)
    if plist is not None:
        try:
            declared = json.loads(plist).get('CFBundleIconFile')
            if isinstance(declared, str) and declared:
                icon = declared if declared.endswith('.icns') else declared + '.icns'
        except (ValueError, AttributeError):
            pass
    if icon is None:
        try:
            icon = next((entry for entry in os.listdir(resources) if entry.endswith('.icns')), None)
        except OSError:
            return None
    if icon is None:
        return None
    icns = join(resources, icon)
    try:
        os.stat(icns)
    except (OSError, ValueError):
        return None
    with tempfile.TemporaryDirectory(prefix='dsh-open-in-app-') as work:
        target = join(work, 'icon.png')
        if await output('sips', ['-s', 'format', 'png', '-Z', '128', icns, '--out', target], timeout_ms, facts) is None:
            return None
        try:
            return Path(target).read_bytes()
        except OSError:
            return None


async def extract_executable_icon_png(executable, timeout_ms, facts):
    with tempfile.TemporaryDirectory(prefix='dsh-open-in-app-') as work:
        script, target = join(work, 'extract-icon.ps1'), join(work, 'icon.png')
        with open(script, 'w', encoding='utf-8', newline='') as stream:
            stream.write(EXTRACT_ICON_PS1)
        ran = await output('powershell.exe', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script, executable, target], timeout_ms, facts)
        if ran is None:
            return None
        try:
            return Path(target).read_bytes()
        except OSError:
            return None


def read_icon_file(path):
    content_type = 'image/png' if path.endswith('.png') else 'image/svg+xml' if path.endswith('.svg') else None
    return dict(bytes=Path(path).read_bytes(), contentType=content_type) if content_type is not None and is_file(path) else None


async def extract_app_icon(app, resolved, timeout_ms, internals=None):
    facts = resolve_internals(internals)
    if facts['platform'] == 'linux':
        desktop_id = (spec_for(app, facts['platform']) or {}).get('desktopId')
        entry = await find_desktop_entry(desktop_id, facts) if desktop_id is not None else None
        icon = (entry or {}).get('icon')
        if not icon:
            return None
        if os.path.isabs(icon):
            return read_icon_file(icon)
        for directory in xdg_data_directories(facts):
            for size in HICOLOR_SIZES + ['scalable']:
                for extension in (['svg'] if size == 'scalable' else ['png', 'svg']):
                    found = read_icon_file(join(directory, 'icons', 'hicolor', size, 'apps', icon + '.' + extension))
                    if found is not None:
                        return found
            for extension in ('png', 'svg'):
                found = read_icon_file(join(directory, 'pixmaps', icon + '.' + extension))
                if found is not None:
                    return found
        return None
    if 'icon' not in resolved:
        return None
    icon = resolved['icon']
    extract = extract_bundle_icon_png if icon['kind'] == 'app-bundle' else extract_executable_icon_png
    data = await extract(icon['path'], timeout_ms, facts)
    return None if data is None else dict(bytes=data, contentType='image/png')
