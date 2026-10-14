"""rc.1 lineage construction and the private JSONL cut boundary."""
import copy
import json

import pytest

from dsh.core.session import Session
from dsh.core.session.json import UNDEFINED
from dsh.core.session.types import validate_rc1_session_header
from dsh.session.lineage_storage import (
    from_header_line, is_header_line, parse_header, parse_header_meta,
    parse_header_record, to_header_line,
)
from dsh.session.projections import SessionProjectionRegistry
from dsh.core.session import SessionStore
from dsh.session.persistence import SessionInspection
from dsh.session.prepared_persistence import PreparedPersistence


def header(seeded=True, **extra):
    return dict(version=0, id='child', createdAt=1, isSeeded=seeded, **extra)


def prefix():
    parent = Session.create('parent')
    parent.append('turn/start', dict(turn=1))
    parent.append('turn/end', dict(turn=1, reason=dict(kind='completed')))
    return parent.snapshotEvents()


def test_exact_cut_keeps_child_owned_constructor_suffix_and_survives_restore():
    inherited = prefix()
    assembled = Session.create('assembled', inherited)
    assembled.append('request/context', dict(provider='provider', model='model'))
    child = Session.create('child', assembled.snapshotEvents(), header(), 2)
    assert child.firstLiveSeq == 4
    assert child.inheritedEventCount == 2
    assert [row['type'] for row in child.ownEvents()] == [
        'session/end-seed', 'request/context', 'session/end-seed']
    assert [child.isOwnSeq(seq) for seq in (-1, 0, 1, 2, 4, 5)] == [False, False, False, True, True, False]
    owned = child.ownEvents()
    child.append('probe/owned', {})
    assert len(owned) == 3
    assert len(child.ownEvents()) == 4
    restored = Session.fromRestore('child', copy.deepcopy(child.snapshotEvents()), child.header, 2)
    assert restored.firstLiveSeq == 6
    assert restored.inheritedEventCount == 2
    assert restored.ownEvents()[:-1] == child.ownEvents()
    assert restored.ownEvents()[-1]['type'] == 'session/end-seed'
    assert 'seedLength' not in restored.header
    assert restored.header.isSeeded is True
    with pytest.raises(TypeError):
        restored.header.is_seeded = False


@pytest.mark.parametrize('seeded', [False, True])
def test_zero_cut_preserves_seeded_identity(seeded):
    child = Session.create('child', [], header(seeded), 0)
    assert child.inheritedEventCount == 0
    assert child.isOwnSeq(0)
    assert child.header.isSeeded is seeded
    physical = to_header_line(child.header, child.inheritedEventCount)
    assert ('seedLength' in physical) is seeded
    storage = from_header_line(physical)
    assert storage.meta.isSeeded is seeded
    assert storage.inheritedEventCount == 0


@pytest.mark.parametrize('seed,meta,cut,message', [
    (None, header(), 0, 'seeded session requires an explicit constructor seed'),
    ([], header(), UNDEFINED, 'seeded session requires an inherited event count'),
    ([], header(False), 1, 'unseeded session inherited event count must be 0'),
    ([], header(), 1, 'session inherited event count exceeds its event log'),
])
def test_inconsistent_lineage_rejected_before_constructor_marker(seed, meta, cut, message):
    with pytest.raises(ValueError, match=message):
        Session.create('child', seed, meta, cut)


@pytest.mark.parametrize('cut', [-1, -0.0, 0.5, 9007199254740992, True, '1', float('inf'), float('nan')])
def test_inherited_cut_is_revalidated(cut):
    with pytest.raises(TypeError, match='SessionLogOffset must be a non-negative safe integer'):
        Session.create('child', [], header(), cut)


@pytest.mark.parametrize('value', [None, UNDEFINED, 0, 1, 'true'])
def test_strict_logical_header_requires_boolean(value):
    record = header()
    record['isSeeded'] = value
    with pytest.raises(ValueError, match='session header isSeeded must be a boolean'):
        validate_rc1_session_header('child', record)


def test_strict_header_rejects_absent_boolean_and_even_undefined_retired_field():
    with pytest.raises(ValueError, match='session header isSeeded must be a boolean'):
        validate_rc1_session_header('child', dict(version=0, id='child', createdAt=1))
    for value in (UNDEFINED, None, 0):
        with pytest.raises(ValueError, match='session header has invalid field "seedLength"'):
            validate_rc1_session_header('child', dict(header(), seedLength=value))


def test_logical_header_copy_preserves_field_and_drops_no_extension():
    validated = validate_rc1_session_header('child', dict(header(), extension={'nested': [1]}))
    detached = copy.deepcopy(validated)
    assert detached.to_dict() == validated.to_dict()
    detached.is_seeded = False
    detached._extra['extension']['nested'].append(2)
    assert validated.isSeeded is True
    assert validated['extension']['nested'] == [1]


@pytest.mark.parametrize('seeded,cut', [(False, UNDEFINED), (False, 0), (True, 0), (True, 2.0)])
def test_private_v0_encoding_and_logical_decoding_are_lossless(seeded, cut):
    logical = validate_rc1_session_header('child', header(seeded, parentSession='parent', delegationDepth=2))
    physical = to_header_line(logical, cut)
    assert 'isSeeded' not in physical
    raw = (json.dumps(physical) + '\n').encode('utf-8')
    storage = parse_header_record(raw)
    assert storage.meta.to_dict() == logical.to_dict()
    assert storage.inheritedEventCount == (0 if cut is UNDEFINED else cut)
    assert to_header_line(storage.meta, storage.inheritedEventCount) == physical
    assert parse_header(raw.decode('utf-8')).inheritedEventCount == storage.inheritedEventCount
    assert parse_header_meta(raw.decode('utf-8')) == logical


@pytest.mark.parametrize('value', [None, True, -1, -0.0, 0.5, '1', 9007199254740992, 10 ** 1000])
def test_invalid_physical_cut_is_not_silently_dropped(value):
    physical = dict(type='session', version=0, id='child', createdAt=1, delegationDepth=0, seedLength=value)
    assert not is_header_line(physical)
    assert parse_header(json.dumps(physical)) is None
    with pytest.raises(ValueError, match='first line is not a session header'):
        parse_header_record((json.dumps(physical) + '\n').encode('utf-8'))


def test_foreign_version_refusal_precedes_lineage_shape_validation():
    with pytest.raises(ValueError, match='upgrade the harness'):
        parse_header_record(b'{"version":1,"id":"future","seedLength":"invalid"}\n')


@pytest.mark.parametrize('field', ['sandboxMode', 'approvalPolicy'])
def test_retired_policy_is_still_rejected(field):
    physical = dict(type='session', version=0, id='child', createdAt=1, delegationDepth=0)
    physical[field] = None
    with pytest.raises(ValueError, match='retired policy baseline fields'):
        parse_header(json.dumps(physical))


def test_encoder_requires_cut_and_consistency():
    with pytest.raises(ValueError, match='seeded session header requires an inherited event count'):
        to_header_line(header())
    with pytest.raises(ValueError, match='unseeded session header inherited event count must be 0'):
        to_header_line(header(False), 1)


def test_projection_init_restore_and_hydrate_receive_exact_cut():
    initialized = []
    def init(meta, cut):
        initialized.append((meta.id, cut))
        return dict(cut=cut, own=[])
    def apply(state, event):
        return (dict(cut=state['cut'], own=state['own'] + [event['seq']])
                if event['seq'] >= state['cut'] else state)
    definition = dict(key='lineage', stateVersion=1, init=init, apply=apply,
                      stateSchema=lambda value: value, wire=dict(view=lambda state: state, viewSchema=lambda value: value))
    child = Session.create('child', prefix(), header(), 2)
    registry = SessionProjectionRegistry()
    registry.register(definition)
    assert registry.snapshot(child)['values']['lineage'] == dict(cut=2, own=[2])
    assert initialized == [('child', 2)]
    checkpoint = registry.checkpoint(child)
    child.append('probe/owned', {})
    restored = registry.restore({}, child.snapshotEvents(), 0, child.header, 2)
    assert restored['snapshot']['values']['lineage'] == dict(cut=2, own=[2, 3])
    assert initialized == [('child', 2), ('child', 2)]
    restored_tail = registry.restore(checkpoint, child.snapshotEvents(2), 2, child.header, 2)
    assert restored_tail['snapshot'] == restored['snapshot']
    # A fresh registry must receive the cut when hydrate triggers a full refold.
    fresh = SessionProjectionRegistry()
    fresh.register(definition)
    assert fresh.hydrate(child, {}, child.snapshotEvents(), 0) == restored['snapshot']
    assert initialized == [('child', 2)] * 3


def test_projection_initialization_failure_is_not_retried_as_legacy_arity():
    invoked = []
    def init(meta, cut):
        invoked.append(cut)
        raise TypeError('initializer body failed')
    registry = SessionProjectionRegistry()
    registry.register(dict(key='broken', stateVersion=1, init=init, stateSchema=lambda value: value,
                           apply=lambda state, event: state))
    with pytest.raises(TypeError, match='initializer body failed'):
        registry.snapshot(Session.create('child', [], header(), 0))
    assert invoked == [0]


def test_store_prepares_new_logical_metadata_and_exact_persistence_cut():
    store = SessionStore()
    child = store.prepare('child', options=dict(seed=prefix(), meta=dict(isSeeded=True), inheritedEventCount=2))
    assert child.header.isSeeded is True
    assert 'seedLength' not in child.header
    assert child.inheritedEventCount == 2
    restored = store.prepare('child', options=dict(seedSource='persistence', seed=child.snapshotEvents(),
                                                  meta=child.header, inheritedEventCount=2))
    assert restored.inheritedEventCount == 2
    assert restored.firstLiveSeq == child.seq
    assert restored.ownEvents() == child.ownEvents()
    metadata = validate_rc1_session_header('child', dict(header(), parentSession='parent'))
    detached = store.prepare('child', options=dict(seed=prefix(), meta=metadata, inheritedEventCount=2))
    assert detached.header.parentSession == 'parent'
    assert metadata.parentSession == 'parent'


def test_new_inspection_cannot_lose_exact_seeded_cut():
    meta = validate_rc1_session_header('child', header())
    with pytest.raises(ValueError, match='seeded session inspection requires an inherited event count'):
        SessionInspection(meta, [])
    view = SessionInspection(meta, [], 0)
    assert view.inheritedEventCount == 0
    assert view.meta.isSeeded is True


@pytest.mark.parametrize('value', [False, None, 0, 1, 'true'])
def test_ignorable_flag_requires_literal_true(value):
    event = dict(type='future/optional', seq=0, time=1, data={}, ignorable=value)
    with pytest.raises(ValueError, match='invalid event envelope'):
        Session.create('child', [event], header(), 0)


def test_ignorable_event_is_retained_and_keeps_sequence_positions():
    event = dict(type='future/optional', seq=0, time=1, data=dict(info='future'), ignorable=True)
    session = Session.fromRestore('child', [event], header(), 0)
    assert session.eventAt(0)['ignorable'] is True
    assert session.eventAt(0)['data'] == dict(info='future')
    assert [row['seq'] for row in session.ownEvents()] == [0, 1]
    assert session.seq == 2


@pytest.mark.asyncio
async def test_prepared_restore_preserves_cut_and_reuses_exact_child():
    original = Session.create('child', prefix(), header(), 2)
    class Backend:
        ctx = None
        async def stored_revision(self, sid):
            return 'fixed-revision'
        async def _inspect_unshared(self, sid):
            return SessionInspection(original.header, copy.deepcopy(original.snapshotEvents()), 2)
    prepared = PreparedPersistence(Backend())
    source = await prepared._source('child')
    assert source.session.inheritedEventCount == 2
    assert source.session.firstLiveSeq == 3
    assert source.session.ownEvents() == original.ownEvents()
    assert source.inspection.inheritedEventCount == 2
    assert source.session.header.isSeeded is True
    await prepared.drain()


@pytest.mark.asyncio
@pytest.mark.parametrize('compression', ['none', 'zstd'])
async def test_canonical_jsonl_retains_ignorable_event_and_tail_cut(tmp_path, compression):
    from dsh.core.session import SessionHeader
    from dsh.session.persistence_jsonl_canonical import JsonlSessionPersistence
    persistence = JsonlSessionPersistence(str(tmp_path), compression=compression)
    meta = SessionHeader('child', created_at=1, seed_length=2)
    optional = dict(type='future/optional', seq=2, time=3, data=dict(info='future'), ignorable=True)
    try:
        await persistence.create(meta)
        await persistence.append('child', list(prefix()) + [optional])
        inspected = await persistence.inspect('child')
        assert inspected.inheritedEventCount == 2
        assert inspected.events[2] == optional
        tail = await persistence.read_from('child', 2)
        assert tail.inheritedEventCount == 2
        assert tail.events == [optional]
        held = await persistence.prepare('child')
        try:
            assert held.session.inheritedEventCount == 2
            assert held.session.ownEvents()[0] == optional
        finally:
            held.dispose()
    finally:
        await persistence.prepared().drain()
        await persistence.close()


@pytest.mark.asyncio
async def test_legacy_sqlite_refuses_marker_without_materializing_partial_log(tmp_path):
    from dsh.core.session import SessionHeader
    from dsh.session.persistence_sqlite_canonical import SqliteSessionPersistence
    persistence = SqliteSessionPersistence(str(tmp_path / 'legacy.db'))
    optional = dict(type='future/optional', seq=0, time=1, data={}, ignorable=True)
    try:
        await persistence.create(SessionHeader('child', created_at=1))
        with pytest.raises(ValueError, match='legacy SQLite format cannot encode ignorable events'):
            await persistence.append('child', [optional])
        assert await persistence.list() == []
        assert persistence.storage().states['child']['cursor'] == 0
    finally:
        await persistence.close()
