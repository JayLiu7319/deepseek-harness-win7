import pytest

from dsh.core.session import Session, SessionSeq, SessionLogOffset
from dsh.core.session.json import UNDEFINED


@pytest.mark.parametrize("brand", [SessionSeq, SessionLogOffset])
@pytest.mark.parametrize("value", [True, False, None, "0", -1, -0.0, 0.1, float("nan"), float("inf"), 9007199254740992, 10 ** 1000])
def test_position_admission_rejects_unsafe_or_non_numeric_values(brand, value):
    with pytest.raises(TypeError, match=brand.__name__ + " must be a non-negative safe integer"):
        brand(value)


@pytest.mark.parametrize("brand", [SessionSeq, SessionLogOffset])
@pytest.mark.parametrize("value", [0, 1, 1.0, 9007199254740991])
def test_position_brand_preserves_valid_value(brand, value):
    assert brand(value) is value


def test_indexed_reads_and_frozen_ranges_remain_stable_after_append():
    session = Session("indexed")
    before = session.snapshotEvents()
    assert session.snapshotEvents() is before
    assert session.eventAt(0) is UNDEFINED
    event = session.append("test/mark", dict(value=1))
    current = session.snapshotEvents()
    assert current is session.snapshotEvents(0, session.seq)
    assert session.eventAt(SessionSeq(0)) is event
    assert session.eventAt(-1) is UNDEFINED
    assert session.eventAt(session.seq) is UNDEFINED
    assert session.snapshotEvents(SessionLogOffset(1.0)) == []
    subset = session.snapshotEvents(0, 1)
    session.append("test/mark", dict(value=2))
    assert before == [] and len(current) == len(subset) == 1
    assert len(session.snapshotEvents()) == 2
    with pytest.raises(TypeError):
        subset.append(event)
    with pytest.raises(TypeError):
        event["data"]["value"] = 3
