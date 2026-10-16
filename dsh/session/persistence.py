"""
Abstract SessionPersistence Seam mounted at `ctx.session_persistence`.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dsh.core.session import SessionHeader
from dsh.core.session.json import UNDEFINED
from dsh.core.session.types import SessionLogOffset


class SessionFormatUnsupportedError(ValueError):
    """Refusal on loading a log written by a newer/unsupported version."""
    name = 'SessionFormatUnsupportedError'

    def __init__(self, message, location=None):
        super().__init__(message)
        self.location = location


class SessionPersistenceNotFoundError(FileNotFoundError):
    name = 'SessionPersistenceNotFoundError'

    def __init__(self, session_id):
        super().__init__('session "%s" not found' % session_id)
        self.sessionId = session_id


class SessionAlreadyExistsError(ValueError):
    name = 'SessionAlreadyExistsError'

    def __init__(self, session_id):
        super().__init__('session "%s" already exists' % session_id)
        self.sessionId = session_id


class SessionAlreadyOwnedError(ValueError):
    name = 'SessionAlreadyOwnedError'

    def __init__(self, session_id):
        super().__init__('session "%s" is already owned by an active write handle' % session_id)
        self.sessionId = session_id


class SessionReadOnlyError(ValueError):
    name = 'SessionReadOnlyError'

    def __init__(self, session_id, operation):
        super().__init__('session "%s": %s is not available on a read handle' % (session_id, operation))
        self.sessionId = session_id


class SessionOwnershipLostError(ValueError):
    name = 'SessionOwnershipLostError'

    def __init__(self, session_id):
        super().__init__('session "%s": write ownership was lost; close this handle and reopen' % session_id)
        self.sessionId = session_id


class SessionHandleClosedError(ValueError):
    name = 'SessionHandleClosedError'

    def __init__(self, session_id, operation):
        super().__init__('session "%s": %s on a closed handle' % (session_id, operation))
        self.sessionId = session_id


class SessionPersistenceCorruptionError(ValueError):
    """Error on reading a corrupt log."""
    name = 'SessionPersistenceCorruptionError'

    def __init__(self, message, options=None):
        super().__init__(message)
        if options is not None and 'cause' in options:
            self.cause = options['cause']
            self.__cause__ = self.cause


def session_format_version_refusal(session_id: str, version: int) -> str:
    return f'session "{session_id}" uses log format v{version}, which was written by a newer harness build; upgrade the harness to read this session'


class SessionLocation:
    """A backend-resolved local artifact location."""

    def __init__(self, kind: str, path: str):
        self.kind = kind
        self.path = path

    def to_dict(self) -> Dict[str, Any]:
        return {"kind": self.kind, "path": self.path}


class SessionStorageMetadata:
    """Logical metadata paired with the exact persisted inheritance cut."""
    def __init__(self, meta: SessionHeader, inherited_event_count: Any):
        self.meta = meta
        self.inherited_event_count = SessionLogOffset(inherited_event_count)

    @property
    def inheritedEventCount(self) -> int:
        return self.inherited_event_count


class SessionInspection(SessionStorageMetadata):
    """Immutable logical session inspection result."""

    def __init__(self, meta: SessionHeader, events: List[Dict[str, Any]], inherited_event_count: Any = UNDEFINED):
        if inherited_event_count is UNDEFINED:
            if meta.isSeeded is True:
                raise ValueError('seeded session inspection requires an inherited event count')
            inherited_event_count = 0
        super().__init__(meta, inherited_event_count)
        self.events = events


class SessionPersistenceSnapshot:
    """Lightweight immutable session summary and revision."""

    def __init__(self, header: SessionHeader, revision: str):
        self.header = header
        self.revision = revision


class SessionReadResult(SessionInspection):
    """Detached suffix read with its admitted storage offset."""

    def __init__(self, meta, events, inherited_event_count, from_seq):
        super().__init__(meta, events, inherited_event_count)
        self.fromSeq = SessionLogOffset(from_seq)


class SessionPersistence(ABC):
    """
    Abstract seam for durable append-only session storage.
    """

    def __init__(self, ctx: Optional[Any] = None):
        self.ctx = ctx
        self._prepared = None
        self._storage = None
        self._storage_locks = {}
        self.prepared_cache_size = 5

    @abstractmethod
    def locate(self, meta: SessionHeader) -> Optional[SessionLocation]:
        """Resolve backend-specific local artifact location without materializing it."""
        raise NotImplementedError

    @abstractmethod
    async def create(self, meta: SessionHeader, inherited_event_count: Any = UNDEFINED) -> None:
        """Register detached metadata; materialize on the first append."""
        raise NotImplementedError

    @abstractmethod
    async def append(self, session_id: str, events: List[Dict[str, Any]]) -> None:
        """Durably append a batch of events in contiguous seq order."""
        raise NotImplementedError

    @abstractmethod
    async def load(self, session_id: str) -> SessionInspection:
        """Load an immutable balanced logical view and commit any required cold crash recovery."""
        raise NotImplementedError

    def storage_lock(self, session_id):
        return self._storage_locks.setdefault(session_id, asyncio.Lock())

    def storage(self):
        from dsh.session.coordinator import PersistenceCoordinator
        if self._storage is None:
            self._storage = PersistenceCoordinator(self)
        return self._storage

    def prepared(self):
        from dsh.session.prepared_persistence import PreparedPersistence
        if self._prepared is None:
            self._prepared = PreparedPersistence(self, self.prepared_cache_size)
        return self._prepared

    async def prepare(self, session_id: str, signal: Optional[Any] = None):
        if hasattr(self, '_load_unshared'):
            return await self.prepared().prepare(session_id, signal)
        # Non-storage test/custom providers retain the minimal preparation seam.
        from dsh.core.session import Session
        from dsh.core.session.preparation import SessionPreparation
        inspection = await self.load(session_id)
        return SessionPreparation.create(Session.from_restore(
            session_id=session_id, seed=inspection.events, header=inspection.meta, ctx=self.ctx,
            inherited_event_count=inspection.inheritedEventCount if inspection.meta.isSeeded is not UNDEFINED else UNDEFINED))

    async def borrowSession(self, session_id, signal=None):
        return await self.prepared().borrow(session_id, signal)

    @abstractmethod
    async def inspect(self, session_id: str, signal: Optional[Any] = None) -> SessionInspection:
        """Inspect an immutable logical session without committing recovery to disk."""
        raise NotImplementedError

    @abstractmethod
    async def read_from(self, session_id: str, from_seq: int) -> SessionInspection:
        """Read stored events from from_seq onward."""
        raise NotImplementedError

    @abstractmethod
    async def list(self, signal: Optional[Any] = None) -> List[SessionHeader]:
        """List all materialized session headers."""
        raise NotImplementedError

    @abstractmethod
    async def list_snapshots(self, signal: Optional[Any] = None) -> List[SessionPersistenceSnapshot]:
        """List metadata and change tokens for all stored sessions."""
        raise NotImplementedError

    async def listSnapshots(self, signal: Optional[Any] = None) -> List[SessionPersistenceSnapshot]:
        return await self.list_snapshots(signal)
