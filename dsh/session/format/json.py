"""Lossless JSON boundary shared by released Session format codecs."""
import math

from dsh.core.session.json import UNDEFINED, deep_freeze, snapshot_json_value
from .error import SessionFormatError


def isSessionFormatJsonObject(value):
    return isinstance(value, dict)


def sessionFormatSafeInteger(value, label):
    if (type(value) not in (int, float) or abs(value) > 9007199254740991
            or not math.isfinite(value) or int(value) != value
            or value == 0 and math.copysign(1, value) < 0):
        raise SessionFormatError(label + ' must be a safe integer')
    return value


def sessionFormatCount(value, label):
    try:
        sessionFormatSafeInteger(value, label)
        if value < 0:
            raise SessionFormatError(label)
    except SessionFormatError:
        raise SessionFormatError(label + ' must be a non-negative safe integer') from None
    return value


def sessionFormatVersion(value, label='Session format version'):
    return sessionFormatCount(value, label)


def inspectSessionFormatVersion(headerValue):
    if not isSessionFormatJsonObject(headerValue):
        raise SessionFormatError('Session header must be a JSON object')
    return sessionFormatVersion(headerValue.get('version', UNDEFINED))


def snapshotSessionFormatJson(value, label='Session value'):
    snapshot = snapshot_json_value(value, UNDEFINED)
    if snapshot is UNDEFINED:
        raise SessionFormatError(label + ' is not lossless JSON')
    return deep_freeze(snapshot)


def snapshotSessionFormatHeader(header, label='Session header'):
    snapshot = snapshotSessionFormatJson(header, label)
    if not isSessionFormatJsonObject(snapshot):
        raise SessionFormatError(label + ' must be a JSON object')
    inspectSessionFormatVersion(snapshot)
    if not isinstance(snapshot.get('id'), str):
        raise SessionFormatError(label + ' id must be a string')
    sessionFormatCount(snapshot.get('createdAt', UNDEFINED), label + ' createdAt')
    if type(snapshot.get('isSeeded')) is not bool:
        raise SessionFormatError(label + ' isSeeded must be a boolean')
    sessionFormatCount(snapshot.get('delegationDepth', UNDEFINED), label + ' delegationDepth')
    return snapshot
