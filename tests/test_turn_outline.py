"""Whole-log outline, raw-view change gating, recovery and scoped ownership."""
import pytest

from dsh.cordis.context import Context
from dsh.core.session import Session
from dsh.session.projections import SessionProjectionRegistry, SessionProjectionsPlugin
from dsh.session.turn_outline import (
    EMPTY_OUTLINE, TURN_OUTLINE_DEFINITION, SessionTurnOutlinePlugin, apply_outline, preview,
)


def message(text, source="user"):
    return dict(content=[dict(type="text", text=text)], source=dict(kind=source, plugin="fixture"))


def test_outline_emits_boundary_first_prompt_and_final_response_only():
    registry, session = SessionProjectionRegistry(), Session("outline")
    registry.register(TURN_OUTLINE_DEFINITION)
    changes = []
    registry.onChanged(lambda s, k, v, seq: changes.append((seq, v)))

    def append(kind, data):
        event = session.append(kind, data, surface_op="append" if kind in ("user/message", "assistant/message") else None)
        registry.on_session_event(session, event)

    append("turn/start", dict(turn=1))
    append("user/message", message("plugin context", "plugin"))
    append("user/message", message("  first\n human prompt  "))
    append("user/message", message("steer keeps opening preview"))
    append("assistant/message", dict(message=dict(role="assistant", content=[dict(type="text", text="draft")])) )
    append("assistant/message", dict(message=dict(role="assistant", content=[dict(type="text", text="final answer")])) )
    append("turn/end", dict(turn=1))
    assert [seq for seq, _ in changes] == [0, 2, 6]
    expected = [dict(turn=1, seq=0, prompt="first human prompt", response="final answer")]
    assert registry.snapshot(session)["values"]["turnOutline"] == expected
    checkpoint = registry.checkpoint(session)
    restored = SessionProjectionRegistry()
    restored.register(TURN_OUTLINE_DEFINITION)
    assert restored.restore(checkpoint, [], session.seq, session.header)["snapshot"]["values"]["turnOutline"] == expected
    restored.hydrate(session, checkpoint, [], session.seq)
    assert restored.cachedSnapshot(session)["values"]["turnOutline"] == expected


def test_retry_boundaries_and_empty_or_nontext_messages_preserve_outline_identity():
    state = apply_outline(EMPTY_OUTLINE, dict(type="turn/start", seq=0, data=dict(turn=2)))
    for turn in (2, 1):
        assert apply_outline(state, dict(type="turn/start", seq=1, data=dict(turn=turn))) is state
    assert apply_outline(state, dict(type="user/message", seq=1, data=message(" "))) is state
    image = dict(type="assistant/message", seq=2, data=dict(message=dict(content=[dict(type="image")])))
    assert apply_outline(state, image) is state
    draft = apply_outline(state, dict(type="assistant/message", seq=3,
        data=dict(message=dict(content=[dict(type="text", text="draft")]))))
    assert draft is not state and draft["turns"] is state["turns"]


@pytest.mark.parametrize("text,limit,expected", [
    (" a\n b\ufeff ", 50, "a b"),
    ("a" * 50, 50, "a" * 49 + "…"),
    ("😀" * 25, 50, "😀" * 24 + "\ud83d…"),
    (" " * 10000, 50, "…"),
    ("a\u0085b", 50, "a\u0085b"),
])
def test_preview_uses_bounded_ecmascript_text_and_utf16_units(text, limit, expected):
    assert preview([dict(type="text", text=text)], limit) == expected


@pytest.mark.parametrize("damage", ["unknown-key", "duplicate-turn", "long-response", "boolean-seq", "bad-draft"])
def test_checkpoint_schema_rejects_corrupted_or_outdated_states(damage):
    state = dict(turns=[dict(turn=0, seq=0, prompt="", response="")], draft="")
    if damage == "unknown-key":
        state["old"] = True
    elif damage == "duplicate-turn":
        state["turns"] += state["turns"]
    elif damage == "long-response":
        state["turns"][0]["response"] = "😀" * 61
    elif damage == "boolean-seq":
        state["turns"][0]["seq"] = True
    else:
        state["draft"] = "x" * 121
    with pytest.raises(ValueError):
        TURN_OUTLINE_DEFINITION["stateSchema"](state)


def test_raw_view_identity_is_compared_before_schema_parses_and_without_listeners():
    registry, session = SessionProjectionRegistry(), Session("gate")
    served, parsed = [], []
    registry.register(dict(key="gate", stateVersion=1, stateSchema=lambda v: v,
        init=lambda header: dict(served=served), apply=lambda state, event: dict(served=state["served"]),
        wire=dict(view=lambda state: state["served"], viewSchema=lambda v: parsed.append(v) or list(v))))
    registry.on_session_event(session, session.append("test/mark", {}))
    assert parsed == []
    changes = []
    remove = registry.onChanged(lambda *args: changes.append(args))
    for _ in range(3):
        registry.on_session_event(session, session.append("test/mark", {}))
    assert len(changes) == len(parsed) == 1
    remove()
    registry.on_session_event(session, session.append("test/mark", {}))
    registry.onChanged(lambda *args: changes.append(args))
    registry.on_session_event(session, session.append("test/mark", {}))
    assert len(changes) == len(parsed) == 2


@pytest.mark.asyncio
async def test_outline_registration_waits_for_provider_and_unloads_without_residue():
    ctx = Context()
    try:
        owner = await ctx.plugin(SessionTurnOutlinePlugin)
        await ctx.plugin(SessionProjectionsPlugin)
        registry = ctx.get("sessionProjections")
        assert registry.has("turnOutline")
        await owner.dispose()
        assert not registry.has("turnOutline")
    finally:
        await ctx.fiber.dispose()
