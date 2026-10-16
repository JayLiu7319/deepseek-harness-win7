"""Canonical raw JSONL basenames for immutable Session generations."""
import re

from .json import sessionFormatVersion

CANONICAL_LOG_FILENAME = re.compile(r'session(?:\.v([1-9][0-9]*))?\.jsonl\Z')


def sessionFormatLogFilename(version):
    generation = sessionFormatVersion(version, 'Session log generation version')
    return 'session.jsonl' if generation == 0 else 'session.v%s.jsonl' % int(generation)


def parseSessionFormatLogFilename(filename):
    match = CANONICAL_LOG_FILENAME.fullmatch(filename)
    if match is None:
        return None
    if match.group(1) is None:
        return 0
    # Reject oversized decimal strings before integer conversion as well.
    digits = match.group(1)
    if len(digits) > 16:
        return None
    version = int(digits)
    return version if version <= 9007199254740991 else None
