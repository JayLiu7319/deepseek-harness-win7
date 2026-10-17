"""rc.3 verified external-application catalog and shell-free detached launches."""
import asyncio
import errno
import json
import os
import re
import subprocess
import sys
import threading
from functools import cmp_to_key
from pathlib import Path

from dsh.core.abort import AbortController
from dsh.host.native_command_current import can_open_native_path, open_native_path, run_native_command
from dsh.subprocess.service import scrubbed_parent_env
from dsh.session.icu_collation import IcuCollator


CATALOG = json.loads((Path(__file__).resolve().parents[1] / 'resources/open_in_app_catalog_current.json').read_text(encoding='utf-8'))
JS_SPACE = '\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff'
APP_PATHS_ROOTS = ['HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths',
                   'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths']
UNINSTALL_ROOTS = ['HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall',
                   'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall',
                   'HKLM\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall']


async def launch_detached_app(command, args, options):
    env = scrubbed_parent_env()
    env.update(options.get('env', {}))
    kwargs = dict(env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        if options.get('windowsHide'):
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startup
    else:
        kwargs['start_new_session'] = True
    child = subprocess.Popen([command] + list(args), **kwargs)
    try:
        deadline = asyncio.get_event_loop().time() + options['watchMs'] / 1000
        while True:
            code = child.poll()
            if code is not None:
                if code != 0:
                    raise RuntimeError('launcher exited with code %s, signal null' % code)
                return
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                return
            await asyncio.sleep(min(0.01, remaining))
    finally:
        # Detached apps outlive the host. Reap eventual POSIX exits without an
        # asyncio task that shutdown would await/cancel, and never kill the app.
        if child.poll() is None:
            threading.Thread(target=child.wait, daemon=True).start()


def resolve_internals(internals=None):
    result = dict(internals or {})
    if result.get('resolveExecutable') is None:
        raise RuntimeError('open-in-app: internals.resolveExecutable is required (the subprocess capability provides it)')
    home = result.setdefault('home', os.path.expanduser('~'))
    for key, value in dict(platform=sys.platform, ssh=False, applicationRoots=['/Applications', join(home, 'Applications')],
                           env=os.environ, run=run_native_command, launch=launch_detached_app).items():
        if result.get(key) is None:
            result[key] = value
    return result


def join(*parts):
    # node:path.join, unlike Python join, does not reset on a later absolute
    # component. Use the actual host path module, independent of probe platform.
    return os.path.normpath(os.sep.join(part for part in parts if part))


async def output(command, args, timeout_ms, internals):
    controller = AbortController()
    timer = asyncio.get_event_loop().call_later(timeout_ms / 1000, controller.abort, TimeoutError('The operation was aborted due to timeout'))
    try:
        return (await internals['run'](command, args, controller.signal))['stdout']
    except Exception:
        return None
    finally:
        timer.cancel()


def is_file(path):
    try:
        return os.path.isfile(path)
    except (OSError, ValueError):
        return False


def is_directory(path):
    try:
        return os.path.isdir(path)
    except (OSError, ValueError):
        return False


def expand_variables(template, pattern, internals):
    missing = []
    def replace(match):
        value = internals['env'].get(match.group(1))
        if value is None:
            missing.append(True)
            return ''
        return value
    value = re.sub(pattern, replace, template)
    return None if missing else value


def expand_candidate(template, internals):
    value = expand_variables(template, r'\$\{([^}]+)\}', internals)
    return join(internals['home'], value[2:]) if value is not None and value.startswith('~/') else value


def expand_registry_value(template, internals):
    return expand_variables(template, r'%([^%]+)%', internals)


def unquote(value):
    return re.sub(r'^"|"$', '', value)


def parse_registry_dump(dump):
    keys, current = {}, None
    for line in re.split(r'\r?\n', dump):
        if line.startswith('HK'):
            current = {}
            keys[line.strip(JS_SPACE)] = current
            continue
        value = re.match(r'^[' + JS_SPACE + r']+(.*?)[' + JS_SPACE + r']+(REG_SZ|REG_EXPAND_SZ)[' + JS_SPACE + r']+(.*)$', line)
        if value is not None and current is not None:
            name, data = value.group(1), value.group(3)
            current['(Default)' if re.match(r'^\(.*\)$', name) else name] = data.strip(JS_SPACE)
    return keys


async def read_windows_registry_view(timeout_ms, internals):
    paths, records = {}, []
    for root in APP_PATHS_ROOTS:
        dump = await output('reg.exe', ['query', root, '/s'], timeout_ms, internals)
        if dump is None:
            continue
        for key, values in parse_registry_dump(dump).items():
            exe, target = key.rsplit('\\', 1)[-1].lower(), values.get('(Default)')
            if not exe.endswith('.exe') or target is None or exe in paths:
                continue
            expanded = expand_registry_value(unquote(target), internals)
            if expanded is not None:
                paths[exe] = expanded
    for root in UNINSTALL_ROOTS:
        dump = await output('reg.exe', ['query', root, '/s'], timeout_ms, internals)
        if dump is None:
            continue
        for values in parse_registry_dump(dump).values():
            if 'DisplayName' in values:
                record = dict(displayName=values['DisplayName'])
                for key in ('InstallLocation', 'DisplayIcon'):
                    if key in values:
                        record[key[0].lower() + key[1:]] = values[key]
                records.append(record)
    return dict(appPaths=paths, installRecords=records)


class RegistryViewOnce:
    def __init__(self, timeout_ms, internals):
        self.timeout_ms, self.internals, self.task = timeout_ms, internals, None

    async def read(self):
        if self.task is None:
            self.task = asyncio.ensure_future(read_windows_registry_view(self.timeout_ms, self.internals))
        return await self.task


def parse_desktop_entry(text):
    active, fields = False, {}
    for line in re.split(r'\r?\n', text):
        line = line.strip(JS_SPACE)
        if line.startswith('['):
            active = line == '[Desktop Entry]'
            continue
        if active and '=' in line:
            key, value = line.split('=', 1)
            key, value = key.strip(JS_SPACE), value.strip(JS_SPACE)
            if key in ('Exec', 'TryExec', 'Icon'):
                fields[dict(Exec='exec', TryExec='tryExec', Icon='icon')[key]] = value
    return fields


def xdg_data_directories(internals):
    env = internals['env']
    home = env.get('XDG_DATA_HOME')
    dirs = env.get('XDG_DATA_DIRS')
    return [join(internals['home'], '.local', 'share') if home is None else home] + [part for part in ('/usr/local/share:/usr/share' if dirs is None else dirs).split(':') if part]


async def find_desktop_entry(desktop_id, internals):
    for directory in xdg_data_directories(internals):
        try:
            return parse_desktop_entry(Path(join(directory, 'applications', desktop_id + '.desktop')).read_text(encoding='utf-8', errors='replace'))
        except (OSError, ValueError):
            pass
    return None


def exec_command(value=None):
    if value is None:
        return None
    match = re.match(r'^"([^"]+)"', value) or re.match(r'^[' + '^' + JS_SPACE + r']+', value)
    return (match.group(1) if match.lastindex else match.group(0)) if match else None


def spec_for(app, platform):
    return app['platforms'].get(platform) if platform in ('darwin', 'win32', 'linux') else None


def executable_launch(path, args, internals, icon=False):
    result = dict(launch=dict(kind='argv', command=path, args=args))
    if icon or internals['platform'] == 'win32':
        result['icon'] = dict(kind='executable', path=path)
    return result


def newest_first(values):
    collator = IcuCollator(locale='en@colNumeric=yes')
    try:
        return sorted(values, key=cmp_to_key(lambda a, b: collator.compare(b, a)))
    finally:
        collator.close()


async def locate(locator, timeout_ms, registry, facts):
    kind = locator['kind']
    if kind == 'fixed':
        result = dict(launch=locator['launch'])
        icon = expand_candidate(locator['iconPath'], facts)
        if icon is not None:
            result['icon'] = dict(kind='executable' if facts['platform'] == 'win32' else 'app-bundle', path=icon)
        return result
    if kind == 'app':
        for root in facts['applicationRoots']:
            for name in locator['fsNames']:
                bundle = join(root, name)
                if is_directory(bundle):
                    return dict(launch=dict(kind='argv', command='open', args=['-a', bundle]), icon=dict(kind='app-bundle', path=bundle))
    elif kind == 'xcode':
        developer = await output('xcode-select', ['-p'], timeout_ms, facts)
        if developer is not None:
            bundle = os.path.dirname(os.path.dirname(developer.strip(JS_SPACE)))
            if bundle.endswith('.app') and is_directory(bundle):
                return dict(launch=dict(kind='argv', command='xed', args=[]), fallbackLaunch=dict(kind='argv', command='open', args=['-a', bundle]), icon=dict(kind='app-bundle', path=bundle))
    elif kind == 'cli':
        if locator.get('requiresDesktop') is True and not can_open_native_path(dict(platform=facts['platform'], env=dict(facts['env']))):
            return None
        path = await facts['resolveExecutable'](locator['name'])
        if path is not None:
            return executable_launch(path, locator['args'], facts)
    elif kind == 'file':
        for candidate in locator['candidates']:
            path = expand_candidate(candidate, facts)
            if path is not None and is_file(path):
                return executable_launch(path, locator['args'], facts)
    elif kind in ('scan', 'github-desktop'):
        root = expand_candidate(locator['root'], facts)
        try:
            entries = os.listdir(root) if root is not None else []
        except (OSError, ValueError):
            return None
        prefix = locator.get('namePrefix', 'app-')
        for version in newest_first([entry for entry in entries if entry.startswith(prefix)]):
            directory = join(root, version)
            path = join(directory, 'GitHubDesktop.exe' if kind == 'github-desktop' else locator['relativeLauncher'])
            if not is_file(path):
                continue
            if kind == 'scan':
                return executable_launch(path, locator['args'], facts)
            cli = join(directory, 'resources', 'app', 'cli.js')
            if is_file(cli):
                return dict(launch=dict(kind='argv', command=path, args=[cli, 'open'], env=dict(ELECTRON_RUN_AS_NODE='1'), windowsHide=True), icon=dict(kind='executable', path=path))
    elif kind == 'app-paths':
        path = (await registry.read())['appPaths'].get(locator['exe'].lower())
        if path is not None and is_file(path):
            return executable_launch(path, locator['args'], facts, icon=True)
    elif kind == 'install-record':
        for record in (await registry.read())['installRecords']:
            if not record['displayName'].startswith(locator['displayNamePrefix']):
                continue
            if 'relativeLauncher' in locator and record.get('installLocation'):
                root = expand_registry_value(unquote(record['installLocation']), facts)
                if root is not None:
                    path = join(root, locator['relativeLauncher'])
                    if is_file(path):
                        return executable_launch(path, locator['args'], facts, icon=True)
            if 'displayIcon' in record:
                path = expand_registry_value(unquote(re.sub(r',-?[0-9]+$', '', record['displayIcon'])).strip(JS_SPACE), facts)
                if path is not None and path.lower().endswith('.exe') and is_file(path):
                    return executable_launch(path, locator['args'], facts, icon=True)
    elif kind == 'desktop':
        entry = await find_desktop_entry(locator['desktopId'], facts)
        if entry is not None:
            candidate = entry.get('tryExec', exec_command(entry.get('exec')))
            if candidate:
                path = candidate if os.path.isabs(candidate) and is_file(candidate) else None if os.path.isabs(candidate) else await facts['resolveExecutable'](candidate)
                if path is not None:
                    return dict(launch=dict(kind='argv', command=path, args=locator['args']))
    else:
        raise RuntimeError('unhandled open-in-app catalog kind: ' + json.dumps(locator, ensure_ascii=False, separators=(',', ':')))
    return None


async def resolve_with_registry(app, timeout_ms, registry, facts):
    spec = spec_for(app, facts['platform'])
    if spec is not None:
        for locator in spec['locators']:
            found = await locate(locator, timeout_ms, registry, facts)
            if found is not None:
                return found
    return None


async def resolve_launch(app, timeout_ms, internals=None):
    facts = resolve_internals(internals)
    return None if facts['ssh'] else await resolve_with_registry(app, timeout_ms, RegistryViewOnce(timeout_ms, facts), facts)


async def resolve_open_in_app_apps(timeout_ms, internals=None):
    facts = resolve_internals(internals)
    if facts['ssh']:
        return {}
    registry = RegistryViewOnce(timeout_ms, facts)
    entries = await asyncio.gather(*(resolve_with_registry(app, timeout_ms, registry, facts) for app in CATALOG))
    return {app['id']: value for app, value in zip(CATALOG, entries) if value is not None}


def missing_executable(error):
    return getattr(error, 'code', None) == 'ENOENT' or getattr(error, 'errno', None) == errno.ENOENT


async def run_launch(launch, path, watch_ms, facts):
    if launch['kind'] == 'shell-open':
        task = asyncio.ensure_future(open_native_path(path, AbortController().signal, dict(platform=facts['platform'], env=facts['env'], run=facts['run'])))
        done, _ = await asyncio.wait([task], timeout=watch_ms / 1000)
        if not done:
            task.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
            return 'launched'
        try:
            task.result()
            return 'launched'
        except Exception as error:
            return 'missing' if missing_executable(error) else 'failed'
    if launch['kind'] != 'argv':
        raise RuntimeError('unhandled open-in-app catalog kind: ' + json.dumps(launch, separators=(',', ':')))
    args = launch['args']
    args = [arg.replace('{path}', path) for arg in args] if any('{path}' in arg for arg in args) else list(args) + [path]
    options = dict(watchMs=watch_ms)
    for key in ('env', 'windowsHide'):
        if key in launch:
            options[key] = launch[key]
    try:
        await facts['launch'](launch['command'], args, options)
        return 'launched'
    except Exception as error:
        return 'missing' if missing_executable(error) else 'failed'


async def launch_resolved(resolved, path, watch_ms, internals=None):
    facts = resolve_internals(internals)
    primary = await run_launch(resolved['launch'], path, watch_ms, facts)
    if primary == 'launched' or 'fallbackLaunch' not in resolved:
        return primary
    fallback = await run_launch(resolved['fallbackLaunch'], path, watch_ms, facts)
    return 'launched' if fallback == 'launched' else 'missing' if 'missing' in (primary, fallback) else 'failed'
