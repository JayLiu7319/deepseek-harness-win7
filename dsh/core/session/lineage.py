"""Exact inherited-prefix ownership for rc.1 Session construction."""
from typing import Any

from dsh.core.session.json import UNDEFINED
from dsh.core.session.types import SessionLogOffset


def inherited_cut(header: Any, explicit_seed: bool, log_length: int, supplied: Any = UNDEFINED) -> int:
    if header.isSeeded and not explicit_seed:
        raise ValueError('seeded session requires an explicit constructor seed')
    if header.isSeeded and supplied is UNDEFINED:
        raise ValueError('seeded session requires an inherited event count')
    cut = SessionLogOffset(0 if supplied is UNDEFINED or supplied is None else supplied)
    if not header.isSeeded and cut != 0:
        raise ValueError('unseeded session inherited event count must be 0')
    if cut > log_length:
        raise ValueError('session inherited event count exceeds its event log')
    return cut
