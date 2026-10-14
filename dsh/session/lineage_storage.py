"""rc.1 logical lineage / private version-0 JSONL header translation.

The physical seedLength field survives only at the storage boundary. Callers
must keep the returned exact cut alongside logical metadata during restore.
Legacy persistence consumers switch to this boundary as one migration batch.
"""
from typing import Any, Dict

from dsh.core.session.json import UNDEFINED
from dsh.core.session.types import SessionLogOffset
from dsh.session.jsonl_format import is_header, parse_json, refuse_version, safe_nonnegative
from dsh.session.sqlite_logical import header_from_stored
from dsh.session.persistence import SessionStorageMetadata


def to_header_line(header: Any, inherited_event_count: Any = UNDEFINED) -> Dict[str, Any]:
    record = header.to_dict() if hasattr(header, 'to_dict') else header
    if record['isSeeded'] and inherited_event_count is UNDEFINED:
        raise ValueError('seeded session header requires an inherited event count')
    cut = SessionLogOffset(0 if inherited_event_count is UNDEFINED or inherited_event_count is None
                           else inherited_event_count)
    if not record['isSeeded'] and cut != 0:
        raise ValueError('unseeded session header inherited event count must be 0')
    result = dict(type='session', version=record['version'], id=record['id'], createdAt=record['createdAt'])
    for name in ('cwd', 'parentSession', 'origin', 'agentPreset'):
        if record.get(name, UNDEFINED) is not UNDEFINED:
            result[name] = record[name]
    if record['isSeeded']:
        result['seedLength'] = cut
    result['delegationDepth'] = record.get('delegationDepth') or 0
    return result


def from_header_line(line: Dict[str, Any]) -> SessionStorageMetadata:
    if 'sandboxMode' in line or 'approvalPolicy' in line:
        raise ValueError('session header uses retired policy baseline fields')
    meta = dict(version=line['version'], id=line['id'], createdAt=line['createdAt'],
                isSeeded=line.get('seedLength', UNDEFINED) is not UNDEFINED,
                delegationDepth=line['delegationDepth'])
    for name in ('cwd', 'parentSession', 'origin', 'agentPreset'):
        if line.get(name, UNDEFINED) is not UNDEFINED:
            meta[name] = line[name]
    supplied = line.get('seedLength', 0)
    cut = SessionLogOffset(0 if supplied is None or supplied is UNDEFINED else supplied)
    return SessionStorageMetadata(header_from_stored(meta), cut)


def is_header_line(value: Any) -> bool:
    return is_header(value) and ('seedLength' not in value or safe_nonnegative(value['seedLength']))


def parse_header(line: str) -> Any:
    try:
        value = parse_json(line)
    except Exception:
        return None
    refuse_version(value)
    return from_header_line(value) if is_header_line(value) else None


def parse_header_meta(line: str) -> Any:
    storage = parse_header(line)
    return None if storage is None else storage.meta


def parse_header_record(record: bytes) -> SessionStorageMetadata:
    if not record or record[-1:] != b'\n' or record.find(b'\n') != len(record) - 1:
        raise ValueError('empty or header-less session log')
    try:
        value = parse_json(record[:-1].decode('utf-8', 'replace'))
    except Exception:
        raise ValueError('corrupt session log: header line is not valid JSON') from None
    refuse_version(value)
    if not is_header_line(value):
        raise ValueError('corrupt session log: first line is not a session header')
    return from_header_line(value)
