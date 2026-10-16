"""Installed current Session boundary used by the build-static format catalog."""
from dsh.core.session.json import UNDEFINED
from dsh.core.session.current import assertSessionEventEnvelope, validateCurrentHeader
from dsh.core.session.current_surface import CurrentSurface
from dsh.core.session.types import SessionLogOffset
from dsh.cordis.utils import _js_strict_equal
from dsh.session.format_v2_to_v3.payload import display


def require_current(header):
    version = header.get('version', UNDEFINED)
    if not _js_strict_equal(version, 3):
        raise ValueError('installed Session format is v3, got v' + display(version))


def validateInstalledCurrentSessionHeader(header):
    require_current(header)
    validateCurrentHeader(header)


def validateInstalledCurrentSessionArtifact(artifact):
    require_current(artifact['header'])
    # Session.fromRestore brands the cut before its constructor validates seed events.
    cut = SessionLogOffset(artifact['inheritedEventCount'])
    header = validateCurrentHeader(artifact['header'])
    events = artifact['events']
    surface = CurrentSurface(events)
    for index, event in enumerate(events):
        assertSessionEventEnvelope(event, index)
        if not _js_strict_equal(event['seq'], index):
            raise ValueError('seed event at index %s has seq %s (expected %s); seed must be contiguous from 0' % (index, event['seq'], index))
        try:
            plan = surface.plan(event, index)
        except Exception as error:
            raise ValueError('invalid seed event at index %s: %s' % (index, error)) from error
        surface.apply(event, plan)
    if not header.isSeeded and cut != 0:
        raise ValueError('unseeded session inherited event count must be 0')
    if cut > len(events):
        raise ValueError('session inherited event count exceeds its event log')
