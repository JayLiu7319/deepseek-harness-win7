"""Wire-zone canonical names from the pinned upstream Node/ICU runtime.

Python's ZoneInfo retains aliases instead of returning Intl's canonical name.
The bundled vocabulary supplies that boundary without depending on OS ICU or
executing Node in a Portable installation. Original Intl lookup ignores case.
"""
import json
import re
from functools import lru_cache
from pathlib import Path

from dsh.cordis.text import trim_js

IANA_TIME_ZONE = re.compile(r'^[A-Za-z][A-Za-z0-9_+.-]*(?:/[A-Za-z0-9_+.-]+)+$')


@lru_cache(maxsize=1)
def _zones():
    return json.loads((Path(__file__).parent / 'resources/time_zones_current.json').read_text(encoding='utf-8'))['zones']


def canonical_client_time_zone(value):
    if not isinstance(value, str) or not value or trim_js(value) != value or value != 'UTC' and IANA_TIME_ZONE.fullmatch(value) is None:
        return None
    canonical = _zones().get(value.lower())
    return canonical if canonical == 'UTC' or canonical is not None and IANA_TIME_ZONE.fullmatch(canonical) is not None else None
