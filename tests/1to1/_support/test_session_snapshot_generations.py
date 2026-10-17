"""Generation admission and ownership controls for the current Web fixture lane."""
import json
import pytest

from .session_snapshot.session_files import (
    parseSessionFixtureName, sessionFixtureFiles, assertSessionFixtureVersion,
)
from .session_snapshot.manifest import parseSnapshotManifest
from .session_snapshot.normalize import scrubModelRequestBulk


def test_selects_latest_generation_per_contiguous_role_without_rewriting_history():
    names = ["session.v2.jsonl", "session.v3.jsonl", "session.1.jsonl", "session.1.v3.jsonl"]
    assert [item["name"] for item in sessionFixtureFiles(names)] == ["session.v3.jsonl", "session.1.v3.jsonl"]
    assert names == ["session.v2.jsonl", "session.v3.jsonl", "session.1.jsonl", "session.1.v3.jsonl"]


@pytest.mark.parametrize("names,reason", [
    (["session.1.v3.jsonl"], "missing parent"),
    (["session.v3.jsonl", "session.2.v3.jsonl"], "contiguous"),
    (["session.v3.jsonl", "session.v3.jsonl"], "duplicate"),
    (["session.v0.jsonl"], "invalid session fixture name"),
    (["session.01.jsonl"], "invalid session fixture name"),
])
def test_rejects_ambiguous_or_incomplete_fixture_roles(names, reason):
    with pytest.raises(ValueError, match=reason):
        sessionFixtureFiles(names)


def test_fixture_generation_matches_header_and_expected_output_is_not_a_replay_role():
    assert parseSessionFixtureName("writer.expected.jsonl") is None
    assert assertSessionFixtureVersion("session.jsonl", '{"type":"session"}\n') == 0
    assert assertSessionFixtureVersion("session.v3.jsonl", '{"type":"session","version":3}\n') == 3
    assert assertSessionFixtureVersion("session.v3.jsonl", '{"type":"session","version":3.0}\n') == 3
    with pytest.raises(ValueError, match="non-negative safe integer"):
        assertSessionFixtureVersion("session.jsonl", '{"type":"session","version":-0.0}\n')
    with pytest.raises(ValueError, match="header declares v2"):
        assertSessionFixtureVersion("session.v3.jsonl", '{"type":"session","version":2}\n')


@pytest.mark.parametrize("metadata,reason", [
    ("version: -1\n  coverage: [multi-hop]", "non-negative safe integer"),
    ("version: 0\n  coverage: []", "non-empty array"),
    ("version: 0\n  coverage: [multi-hop, multi-hop]", "unique supported"),
    ("version: 0\n  coverage: [unknown]", "unique supported"),
])
def test_rejects_invalid_historical_format_metadata(metadata, reason):
    with pytest.raises(ValueError, match=reason):
        parseSnapshotManifest("version: 1\nprofile: web\nsessionFormat:\n  " + metadata + "\n")


def test_historical_format_requires_owning_manifest():
    text = "version: 1\nprofile: web\nsessionFormat:\n  version: 2\n  coverage: [adjacent-migration]\n"
    assert parseSnapshotManifest(text)["sessionFormat"] == dict(version=2, coverage=["adjacent-migration"])
    with pytest.raises(ValueError, match="only valid when the scenario owns"):
        parseSnapshotManifest(text + "session:\n  source: ../owner/session.v2.jsonl\n")


def test_current_request_bulk_scrubber_keeps_business_text_and_other_header_fields():
    rows = [
        dict(type="system/message", data=dict(message=dict(content=[dict(type="text", text="private prompt")]))),
        dict(type="user/message", data=dict(content=[dict(type="text", text="user authored") ])),
        dict(type="request/header", data=dict(header=dict(tools=[dict(name="tool")], model="fixture"))),
    ]
    raw = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n"
    result = [json.loads(line) for line in scrubModelRequestBulk(raw).splitlines()]
    assert result[0]["data"]["message"]["content"][0]["text"] == "{{system}}"
    assert result[1] == rows[1]
    assert result[2]["data"]["header"] == dict(tools="{{tools}}", model="fixture")
    assert scrubModelRequestBulk(scrubModelRequestBulk(raw)) == scrubModelRequestBulk(raw)
