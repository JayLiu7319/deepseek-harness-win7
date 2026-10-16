"""Pure rc.3 library contracts; active Session writer remains a separate migration."""
import json
from pathlib import Path

import pytest

from dsh.session.format import SessionFormatError, snapshotSessionFormatJson, sessionFormatCount
from scripts.oracles.session_format_python import observe
from scripts import session_format_oracle

CORPUS = json.loads((Path(__file__).resolve().parents[1] / 'scripts/oracles/session_format_cases.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CORPUS, ids=[case['case'] for case in CORPUS])
def test_format_admission_migration_and_restore_contract(case):
    actual = observe(case)
    expected = case['expected']
    assert actual['outcome'] == expected['outcome'], actual
    if 'name' in expected:
        assert actual['name'] == expected['name'], actual
    if 'value' in expected:
        assert actual['value'] == expected['value']
    if 'status' in expected:
        assert actual['value']['status'] == expected['status']


def test_two_edges_preserve_order_and_transform_compact_runs():
    value = observe(dict(case='stream', kind='chain', edges=[dict(first=0, tail=True), dict(first=1, tail=True)]))['value']
    assert value['header']['version'] == 2
    assert value['stages'] == [dict(first=0, sourceKind='decoded', sourceCut=0),
        dict(first=1, sourceKind='transformed', sourceCut=0)]
    assert value['events'] == [dict(seq=i, hops=[0, 1]) for i in range(3)] + [
        dict(tail=0, hops=[1]), dict(tail=1)]


def test_snapshot_detaches_and_freezes_nested_values_without_modifying_caller():
    borrowed = {'nested': {'items': [1, {'name': 'before'}]}}
    frozen = snapshotSessionFormatJson(borrowed)
    borrowed['nested']['items'][1]['name'] = 'after'
    assert frozen['nested']['items'][1]['name'] == 'before'
    with pytest.raises(TypeError):
        frozen['nested']['items'].append(3)
    with pytest.raises(TypeError):
        frozen['nested']['items'][1]['name'] = 'changed'


def test_python_unbounded_integer_is_refused_with_format_error():
    with pytest.raises(SessionFormatError, match='non-negative safe integer'):
        sessionFormatCount(10 ** 1000, 'count')


def test_paired_runner_refuses_wrong_source_and_preserves_failed_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(session_format_oracle, 'ROOT', tmp_path)
    monkeypatch.setattr('sys.argv', ['oracle', '--source', str(tmp_path/'source'),
        '--output-dir', str(tmp_path/'.goose/out/pair')])
    monkeypatch.setattr(session_format_oracle.subprocess, 'check_output', lambda *args, **kwargs: 'wrong-pin\n')
    assert session_format_oracle.main() == 2
    receipt = tmp_path/'.goose/out/pair/report.json'
    previous = receipt.read_bytes()
    report = json.loads(previous)
    assert report['status'] == 'runner-error'
    assert report['cases'] == []
    assert 'Unchanged rc.3 Source required' in report['error']
    with pytest.raises(FileExistsError):
        session_format_oracle.main()
    assert receipt.read_bytes() == previous


def test_paired_runner_rejects_duplicate_explicit_corpus_before_launch(tmp_path, monkeypatch):
    monkeypatch.setattr(session_format_oracle, 'ROOT', tmp_path)
    corpus = tmp_path/'duplicates.json'
    corpus.write_text('[{"case":"same"},{"case":"same"}]', encoding='utf-8')
    monkeypatch.setattr('sys.argv', ['oracle', '--source', str(tmp_path/'source'), '--corpus', str(corpus),
        '--output-dir', str(tmp_path/'.goose/out/duplicates')])
    monkeypatch.setattr(session_format_oracle.subprocess, 'check_output',
        lambda args, **kwargs: session_format_oracle.TARGET if args[-1] == 'HEAD' else '')
    assert session_format_oracle.main() == 2
    result = json.loads((tmp_path/'.goose/out/duplicates/report.json').read_text(encoding='utf-8'))
    assert result['commands'] == []
    assert result['error'] == 'Empty or duplicate corpus cases'


def test_paired_comparison_keeps_boolean_and_number_distinct():
    assert not session_format_oracle.json_equal({'cut': False}, {'cut': 0})
    assert not session_format_oracle.json_equal([1], [True])
    assert not session_format_oracle.json_equal({'cut': 0}, {'cut': 0, 'other': None})
    assert session_format_oracle.json_equal({'cut': 0.0}, {'cut': 0})
