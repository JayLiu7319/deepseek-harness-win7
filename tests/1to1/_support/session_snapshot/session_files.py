"""Immutable fixture generations, matching session-snapshot/src/session-files.ts."""
import json
import math
import re

FIXTURE_FILE = re.compile(r"^session(?:\.([1-9]\d*))?(?:\.v([1-9]\d*))?\.jsonl$")


def nonNegativeSafeInteger(value):
    return (type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 9007199254740991
            and value == int(value) and not (value == 0 and math.copysign(1, value) < 0))


def parseSessionFixtureName(name):
    match = FIXTURE_FILE.fullmatch(name)
    if match is None:
        if name.startswith("session") and name.endswith(".jsonl"):
            raise ValueError("invalid session fixture name: " + name)
        return None
    index, version = (int(part or 0) for part in match.groups())
    if max(index, version) > 9007199254740991:
        raise ValueError("invalid session fixture name: " + name)
    return dict(index=index, version=version, name=name)


def sessionFixtureName(index, version):
    for value, label in ((index, "session fixture index"), (version, "Session format version")):
        if not nonNegativeSafeInteger(value):
            raise ValueError(label + " must be a non-negative safe integer")
    return "session%s%s.jsonl" % (".%d" % index if index else "", ".v%d" % version if version else "")


def sessionFixtureFiles(names):
    selected, identities = {}, set()
    for name in names:
        fixture = parseSessionFixtureName(name)
        if fixture is None:
            continue
        identity = (fixture["index"], fixture["version"])
        if identity in identities:
            raise ValueError("duplicate session fixture generation: " + name)
        identities.add(identity)
        previous = selected.get(fixture["index"])
        if previous is None or fixture["version"] > previous["version"]:
            selected[fixture["index"]] = fixture
    if 0 not in selected:
        raise ValueError("missing parent session fixture")
    ordered = sorted(selected.values(), key=lambda item: item["index"])
    for offset, fixture in enumerate(ordered):
        if fixture["index"] != offset:
            raise ValueError("session fixture roles must be contiguous: expected index %d, found %s" % (offset, fixture["name"]))
    return ordered


def assertSessionFixtureVersion(name, content):
    fixture = parseSessionFixtureName(name)
    if fixture is None:
        raise ValueError("not a session fixture name: " + name)
    first = next((line for line in content.splitlines() if line.strip()), None)
    if first is None:
        raise ValueError(name + ": session fixture is empty")
    header = json.loads(first)
    if not isinstance(header, dict) or header.get("type") != "session":
        raise ValueError(name + ": first record must be a Session header")
    version = header.get("version", 0)
    if not nonNegativeSafeInteger(version):
        raise ValueError(name + ": Session header version must be a non-negative safe integer")
    if version != fixture["version"]:
        raise ValueError("%s: filename declares Session format v%d, header declares v%d" % (name, fixture["version"], version))
    return version
