"""Recoverable Desktop package publication, committed only after Host readiness.

Only managed Python plugin trees are copied; profile junctions, user settings,
sessions and arbitrary node_modules are never traversed or restored.
"""
import base64
import json
import os
import shutil
import stat
import uuid
from pathlib import Path

from dsh.boot import python_plugins as store
from dsh.boot import python_plugin_versions as versions
from dsh.boot.profile_lease import ProfileLease

JOURNAL = '.dsh-desktop-health.json'
WORK = '.dsh-desktop-health'
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024


def path(directory, relative):
    return Path(versions.owned_path(str(directory), relative))


def save(directory, state):
    store.atomic_bytes(str(path(directory, JOURNAL)), store.json_bytes(state))


def read(directory):
    journal = path(directory, JOURNAL)
    if not journal.exists():
        return None
    state = json.loads(journal.read_text(encoding='utf-8'))
    if (state.get('formatVersion') != 1 or state.get('phase') not in ('pending', 'committed') or
            not isinstance(state.get('token'), str) or len(state['token']) != 32 or
            any(char not in '0123456789abcdef' for char in state['token'])):
        raise ValueError('Invalid Desktop health transaction; preserve it for inspection')
    store.package_name(state['name'])
    return state


def copy_tree(source, target, budget):
    target.mkdir(parents=True, exist_ok=True)
    for relative, filename in store.regular_tree(str(source)):
        budget[0] += os.path.getsize(filename)
        if budget[0] > MAX_SNAPSHOT_BYTES:
            raise ValueError('Desktop package snapshot exceeds 256 MiB')
        destination = path(target, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(filename, str(destination))


def verify(target, expected):
    if expected is None:
        if target.exists():
            raise RuntimeError('Unexpected Desktop plugin tree; recovery requires inspection')
    else:
        versions.verify(str(target), expected)


def remove_workspace(workspace):
    # A transaction can contain several independently bounded plugin trees.
    # Validate ownership without applying one plugin's byte/file cap to their
    # combined snapshot, and never follow a user-inserted junction on cleanup.
    if store.reparse(str(workspace)):
        raise ValueError('Desktop workspace must not be a link or junction')
    for root, directories, files in os.walk(str(workspace)):
        for name in directories + files:
            item = os.path.join(root, name)
            if store.reparse(item) or not (stat.S_ISDIR(os.lstat(item).st_mode) or stat.S_ISREG(os.lstat(item).st_mode)):
                raise ValueError('Desktop workspace contains an unowned link or special file')
    store.remove_directory(str(workspace))


def clean(directory, state):
    workspace = path(directory, WORK + '/' + state['token'])
    if workspace.exists():
        # Verify all ancestors and every remaining entry before recursive removal.
        remove_workspace(workspace)
    path(directory, JOURNAL).unlink()


def prepare(directory, operation, value, expected_name=None):
    from dsh.host.desktop.plugins import mutate
    directory = str(Path(directory).resolve())
    with ProfileLease(directory, exclusive=True):
        store.recover(directory)
        if read(directory) is not None:
            raise RuntimeError('Pending Desktop health transaction; recover it first')
        before = path(directory, 'package.json').read_bytes()
        manifest = json.loads(before)
        token = uuid.uuid4().hex
        workspace = path(directory, WORK + '/' + token)
        shadow = workspace / 'candidate'
        shadow.mkdir(parents=True)
        published = False
        try:
            (shadow / 'package.json').write_bytes(before)
            budget = [0]
            for name, record in manifest.get('dsh', {}).get('pythonPlugins', {}).items():
                source = Path(store.destination(directory, name))
                verify(source, record['files'])
                copy_tree(source, Path(store.destination(str(shadow), name)), budget)
                for old in record.get('history', []):
                    source = Path(versions.archive_path(directory, name, old))
                    verify(source, old['files'])
                    copy_tree(source, Path(versions.archive_path(str(shadow), name, old)), budget)
            name = mutate(str(shadow), operation, value, expected_name)
            after = (shadow / 'package.json').read_bytes()
            current = json.loads(after)
            old = manifest.get('dsh', {}).get('pythonPlugins', {}).get(name)
            new = current.get('dsh', {}).get('pythonPlugins', {}).get(name)
            state = dict(formatVersion=1, phase='pending', token=token, name=name, operation=operation,
                before=base64.b64encode(before).decode('ascii'), after=base64.b64encode(after).decode('ascii'),
                old=old, new=new)
            target = Path(store.destination(directory, name))
            verify(target, old['files'] if old else None)
            if path(directory, 'package.json').read_bytes() != before:
                raise RuntimeError('Desktop profile changed during preparation')
            save(directory, state)
            published = True
            if old is not None:
                store.replace_directory(str(target), str(workspace / 'previous'))
            if new is not None:
                store.replace_directory(store.destination(str(shadow), name), str(target))
            store.atomic_bytes(str(path(directory, 'package.json')), after)
            return name
        except BaseException:
            if published:
                _rollback(directory, state)
            elif workspace.exists():
                remove_workspace(workspace)
            raise


def _rollback(directory, state):
    before, after = (base64.b64decode(state[key], validate=True) for key in ('before', 'after'))
    current = path(directory, 'package.json').read_bytes()
    if current not in (before, after):
        raise RuntimeError('Desktop profile changed outside transaction; recovery requires inspection')
    target = Path(store.destination(directory, state['name']))
    previous = path(directory, WORK + '/' + state['token'] + '/previous')
    old, new = state['old'], state['new']
    if target.exists():
        files = store.file_hashes(str(target))
        if files not in [record['files'] for record in (old, new) if record is not None]:
            raise RuntimeError('Desktop plugin changed outside transaction; recovery requires inspection')
    if old is not None:
        if previous.exists():
            verify(previous, old['files'])
            if target.exists():
                store.remove_directory(str(target))
            store.replace_directory(str(previous), str(target))
        else:
            verify(target, old['files'])
    elif target.exists():
        verify(target, new['files'])
        store.remove_directory(str(target))
    store.atomic_bytes(str(path(directory, 'package.json')), before)
    clean(directory, state)


def _finish(directory, state):
    after = base64.b64decode(state['after'], validate=True)
    if path(directory, 'package.json').read_bytes() != after:
        raise RuntimeError('Desktop committed profile changed; preserve transaction for inspection')
    target = Path(store.destination(directory, state['name']))
    verify(target, state['new']['files'] if state['new'] else None)
    previous = path(directory, WORK + '/' + state['token'] + '/previous')
    if state['operation'] == 'upgrade':
        archive = Path(versions.archive_path(str(directory), state['name'], state['old']))
        if archive.exists():
            verify(archive, state['old']['files'])
        else:
            verify(previous, state['old']['files'])
            archive.parent.mkdir(parents=True, exist_ok=True)
            store.replace_directory(str(previous), str(archive))
    clean(directory, state)


def commit(directory):
    # Host holds a shared lease while healthy. This shared lease excludes every
    # installer, and commit only records readiness and retires owned snapshots.
    with ProfileLease(str(directory)):
        state = read(directory)
        if state is None:
            raise RuntimeError('No Desktop health transaction to commit')
        after = base64.b64decode(state['after'], validate=True)
        if path(directory, 'package.json').read_bytes() != after:
            raise RuntimeError('Desktop profile changed before health commit')
        verify(Path(store.destination(str(directory), state['name'])), state['new']['files'] if state['new'] else None)
        state['phase'] = 'committed'
        save(directory, state)
        _finish(directory, state)


def recover(directory):
    with ProfileLease(str(directory), exclusive=True):
        store.recover(str(directory))
        state = read(directory)
        if state is not None:
            (_finish if state['phase'] == 'committed' else _rollback)(directory, state)
