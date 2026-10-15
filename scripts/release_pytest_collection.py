"""Fail before test execution when required parameter instances drift."""
import json
import os
from pathlib import Path

import pytest
from _pytest.junitxml import mangle_test_address

from scripts.verify_release import validate_regression_collection


def pytest_collection_finish(session):
    rows = []
    for item in session.items:
        address = mangle_test_address(item.nodeid)
        rows.append(dict(classname='.'.join(address[:-1]), name=address[-1]))
    report = dict(format='dsh-regression-collection@1', items=rows,
                  scope='Collection identities only; no test execution or acceptance is implied.')
    try:
        report.update(validate_regression_collection(rows), result='collection-valid')
    except RuntimeError as error:
        report.update(result='refused', error=str(error))
    path = Path(os.environ['DSH_RELEASE_COLLECTION_REPORT'])
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write('\n')
    if report['result'] == 'refused':
        pytest.exit(report['error'], returncode=4)
