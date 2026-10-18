"""Preserve the encoding of an existing default Desktop session directory.

This is an application upgrade policy, not a persistence format migration.
Explicit user configuration and the backend's mixed-encoding guard still win.
"""
import os
import stat

from dsh.boot.profile import compose_entries
from dsh.cordis.environment import resolve_dsh_home
from dsh.session.jsonl_current import parseGenerationLogFilename


def _plain_entry(entry, directory):
    metadata = entry.stat(follow_symlinks=False)
    if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
        return False
    return stat.S_ISDIR(metadata.st_mode) if directory else stat.S_ISREG(metadata.st_mode)


def _directories(path):
    try:
        with os.scandir(path) as entries:
            return [entry.path for entry in entries if _plain_entry(entry, True)]
    except FileNotFoundError:
        return []


def _encodings(root):
    if os.path.lexists(root):
        metadata = os.lstat(root)
        if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, 'st_file_attributes', 0) & 0x400:
            return set()
    found = set()
    for project in _directories(root):
        for session in _directories(project):
            with os.scandir(session) as entries:
                for entry in entries:
                    if not _plain_entry(entry, False):
                        continue
                    for encoding in ('none', 'zstd'):
                        if parseGenerationLogFilename(entry.name, encoding) is not None:
                            found.add(encoding)
                    if len(found) == 2:
                        return found
    return found


def preserve_default_session_encoding(patches):
    """Return a detached patch list; never edit a user config or session file."""
    entries = compose_entries([patches])
    for entry in entries:
        config = entry.get('config')
        if (entry.get('id') != 'session-persistence-jsonl'
                or entry.get('name') != '@deepseek-ai/dsh-session-persistence-jsonl'
                or entry.get('disabled')
                or not isinstance(config, dict)
                or config.get('root') != {'__jsExpr': "dshHomePath('sessions')"}
                or 'compression' in config):
            continue
        if _encodings(os.path.join(resolve_dsh_home(), 'sessions')) == {'none'}:
            # Cordis replaces the entire config: retain every effective field.
            return list(patches) + [dict(id=entry['id'], config=dict(config, compression='none'))]
    return list(patches)
