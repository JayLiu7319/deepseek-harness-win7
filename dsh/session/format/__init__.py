"""Pure Session-format machinery; released codecs are supplied by the catalog owner.

This library does not change the active writer or mount a persistence backend.
"""
from .error import SessionFormatError, SessionFormatUnsupportedMigrationError
from .json import (isSessionFormatJsonObject, sessionFormatCount, sessionFormatSafeInteger,
    sessionFormatVersion, inspectSessionFormatVersion, snapshotSessionFormatJson, snapshotSessionFormatHeader)
from .filename import sessionFormatLogFilename, parseSessionFormatLogFilename
from .chain import defineSessionFormatMigration, createSessionFormatChain, SessionFormatEventCollector
from .catalog import createSessionFormatCatalog
