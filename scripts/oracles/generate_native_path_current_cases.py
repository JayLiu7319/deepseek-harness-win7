"""Generate input corpus; expected observations are frozen from unchanged rc.3 Source."""
import json
from pathlib import Path

cases = []
def add(name, operation='open', path="C:/project/a, b's #?.txt", platform='win32', **values):
    cases.append(dict(case=name, kind='native-path-current', operation=operation, path=path, facts=dict(platform=platform, **values.pop('facts', {})), **values))

for platform in ('win32', 'darwin', 'linux', 'freebsd'):
    add('facts-' + platform, 'facts', platform=platform)
    add('open-' + platform, platform=platform)
    add('text-' + platform, 'text', platform=platform)
    add('reveal-' + platform, 'reveal', platform=platform)
for marker in ('DISPLAY', 'WAYLAND_DISPLAY', 'WSL_DISTRO_NAME', 'WSL_INTEROP'):
    add('facts-' + marker, 'facts', platform='linux', facts=dict(env={marker:'yes'}))
    add('facts-empty-' + marker, 'facts', platform='linux', facts=dict(env={marker:''}))
for release in ('5.15.0-Microsoft-standard', 'generic'):
    add('facts-kernel-' + release, 'facts', platform='linux', facts=dict(osRelease=release))
for extension in ('html', 'HTM', 'xhtml', 'svg', 'txt'):
    add('browser-linux-' + extension, path='/tmp/view.'+extension, platform='linux', facts=dict(env=dict(BROWSER='browser --literal')))
    add('editor-linux-' + extension, 'text', path='/tmp/view.'+extension, platform='linux', facts=dict(env=dict(BROWSER='browser')))
for label, output in (
    ('bundle', '{ LSHandlerRoleAll = "org.browser"; LSHandlerURLScheme = https; }'),
    ('nested', '{ LSHandlerPreferredVersions = { LSHandlerRoleAll = 0; }; LSHandlerURLScheme = "https"; LSHandlerRoleAll = org.real; }'),
    ('http-only', '{ LSHandlerRoleAll = org.other; LSHandlerURLScheme = http; }'),
    ('empty', ''),
):
    add('browser-mac-' + label, path='/tmp/view.html', platform='darwin', replies=dict(defaults=dict(stdout=output)))
add('browser-mac-defaults-failed', path='/tmp/view.svg', platform='darwin', replies=dict(defaults=dict(error='no preference')))
add('browser-mac-launch-failed', path='/tmp/view.svg', platform='darwin', replies=dict(defaults=dict(stdout='{ LSHandlerRoleAll = org.browser; LSHandlerURLScheme = https; }'), open=dict(error='launch rejected')))
add('browser-linux-failed', path='/tmp/view.svg', platform='linux', facts=dict(env=dict(BROWSER='browser')), replies=dict(browser=dict(error='launch rejected')))
for operation in ('open', 'text', 'reveal'):
    for label, reply in (('translated', dict(stdout="C:\\用户\\a,b's.html\r\n")), ('empty', dict(stdout='\r\n')), ('failed', dict(error='translation rejected')), ('aborted', dict(stdout='C:\\ok',abort=True))):
        add('wsl-' + operation + '-' + label, operation, path='/tmp/a.html', platform='linux', facts=dict(env=dict(WSL_INTEROP='wsl', BROWSER='ignored')), replies=dict(wslpath=reply))
for label, path in (('drive', 'C:\\目录\\a, b#?%.txt'), ('unc', '\\\\server\\share\\a, b.txt'), ('unicode-server', '\\\\服务器\\share\\文档.txt'), ('dots','C:\\a\\..\\b.txt')):
    add('explorer-uri-' + label, 'reveal', path=path)
for code in (1, '1', 2, 0):
    add('explorer-exit-' + repr(code), 'reveal', replies={'explorer.exe':dict(error='handoff',code=code)})
add('explorer-aborted-handoff', 'reveal', replies={'explorer.exe':dict(error='handoff',code=1,abort=True)})
for operation in ('open', 'text', 'reveal'):
    add('pre-aborted-' + operation, operation, aborted=True)

if __name__ == '__main__':
    Path(__file__).with_name('native_path_current_cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
