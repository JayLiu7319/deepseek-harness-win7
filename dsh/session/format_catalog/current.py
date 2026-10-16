"""Installed current Session boundary used by the build-static format catalog."""
from dsh.core.session.json import UNDEFINED
from dsh.core.session.types import SessionLogOffset
from dsh.cordis.utils import _js_strict_equal
from dsh.session.format_v2_to_v3.payload import display


def require_current(header):
    version = header.get('version', UNDEFINED)
    if not _js_strict_equal(version, 3):
        raise ValueError('installed Session format is v3, got v' + display(version))


def validateInstalledCurrentSessionHeader(header):
    require_current(header)
    from dsh.core.session.current_session import CurrentSession
    CurrentSession.from_restore(header.get('id',UNDEFINED), [], header, SessionLogOffset(0), 'detached')


def validateInstalledCurrentSessionArtifact(artifact):
    require_current(artifact['header'])
    from dsh.core.session.current_session import CurrentSession
    # This provider brands the cut before the constructor validates seed events.
    cut = SessionLogOffset(artifact['inheritedEventCount'])
    CurrentSession.from_restore(artifact['header'].get('id',UNDEFINED), artifact['events'],
        artifact['header'], cut, 'detached')
