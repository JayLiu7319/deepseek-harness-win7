"""Persisted feedback admission matching the current Zod object schemas."""
import json
import math
import re

from dsh.cordis.text import trim_js
from dsh.core.session.json import UNDEFINED
from dsh.feedback.session_current import FEEDBACK_CATEGORIES

UUID_PATTERN = r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)$'


class ZodError(ValueError):
    name = 'ZodError'

    def __init__(self, issues):
        self.issues = issues
        super().__init__(json.dumps(issues, ensure_ascii=False, indent=2))


def validate_feedback(data, put):
    issues = []
    def invalid(expected, value, path):
        received = ('undefined' if value is UNDEFINED else 'null' if value is None else
                    'boolean' if type(value) is bool else 'number' if type(value) in (int, float) else
                    'string' if isinstance(value, str) else 'array' if isinstance(value, list) else 'object')
        issues.append(dict(expected=expected, code='invalid_type', path=path,
                           message='Invalid input: expected {}, received {}'.format(expected, received)))
    def string(value, path, minimum=False):
        if not isinstance(value, str):
            invalid('string', value, path)
            return False
        if minimum and not value:
            issues.append(dict(origin='string', code='too_small', minimum=1, inclusive=True,
                               path=path, message='Too small: expected string to have >=1 characters'))
        return True
    def enum(value, choices, path):
        if value not in choices:
            issues.append(dict(code='invalid_value', values=list(choices), path=path,
                               message='Invalid option: expected one of ' + '|'.join(json.dumps(choice) for choice in choices)))
    def timestamp(value, path):
        if type(value) not in (int, float) or not math.isfinite(value):
            invalid('number', value, path)
            return False
        if value != int(value):
            issues.append(dict(expected='int', format='safeint', code='invalid_type', path=path,
                               message='Invalid input: expected int, received number'))
            return False
        if abs(value) > 9007199254740991:
            too_big = value > 0
            limit = 9007199254740991 if too_big else -9007199254740991
            issues.append(dict(code='too_big' if too_big else 'too_small',
                               **({'maximum': limit} if too_big else {'minimum': limit}),
                               note='Integers must be within the safe integer range.', origin='int', inclusive=True,
                               path=path, message=('Too big: expected int to be <=9007199254740991' if too_big else 'Too small: expected int to be >=-9007199254740991')))
        if value < 0:
            issues.append(dict(origin='number', code='too_small', minimum=0, inclusive=True,
                               path=path, message='Too small: expected number to be >=0'))
        if value > 9007199254740991:
            issues.append(dict(origin='number', code='too_big', maximum=9007199254740991, inclusive=True,
                               path=path, message='Too big: expected number to be <=9007199254740991'))
        return True
    if not isinstance(data, dict):
        invalid('object', data, [])
    else:
        string(data.get('sessionId', UNDEFINED), ['sessionId'], True)
        if not put:
            string(data.get('messageId', UNDEFINED), ['messageId'], True)
        else:
            item = data.get('item', UNDEFINED)
            if not isinstance(item, dict):
                invalid('object', item, ['item'])
            else:
                string(item.get('messageId', UNDEFINED), ['item', 'messageId'], True)
                enum(item.get('rating', UNDEFINED), ('positive', 'negative'), ['item', 'rating'])
                if 'note' in item and string(item['note'], ['item', 'note']) and not trim_js(item['note']):
                    issues.append(dict(code='custom', path=['item', 'note'], message='Invalid input'))
                if 'category' in item:
                    enum(item['category'], FEEDBACK_CATEGORIES, ['item', 'category'])
                version = item.get('version', UNDEFINED)
                if string(version, ['item', 'version']) and re.fullmatch(UUID_PATTERN, version) is None:
                    issues.append(dict(origin='string', code='invalid_format', format='uuid', pattern='/' + UUID_PATTERN + '/',
                                       path=['item', 'version'], message='Invalid UUID'))
                created = timestamp(item.get('createdAt', UNDEFINED), ['item', 'createdAt'])
                updated = timestamp(item.get('updatedAt', UNDEFINED), ['item', 'updatedAt'])
                if created and updated and item['updatedAt'] < item['createdAt']:
                    issues.append(dict(code='custom', path=['item'], message='Invalid input'))
    if issues:
        raise ZodError(issues)
