"""Browser-safe @ token grammar, shared by file-reference providers."""
import re
from typing import Any, Dict, Optional

_SPACE = r"\u0009-\u000d\u0020\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_QUOTED = re.compile(r'(?:^|[' + _SPACE + r'])(@"([^"]*))$')
_PLAIN = re.compile(r'(?:^|[' + _SPACE + r'])(@([^' + _SPACE + r']*))$')

class ActiveAtToken:
    def __init__(self, prefix: str, query: str, quoted: bool):
        self.prefix, self.query, self.quoted = prefix, query, quoted

    def to_dict(self) -> Dict[str, Any]:
        return dict(prefix=self.prefix, query=self.query, quoted=self.quoted)

def active_at_token(line: str, cursor_col: int) -> Optional[ActiveAtToken]:
    units = line.encode("utf-16-le", "surrogatepass")
    end = max(len(units) // 2 + cursor_col, 0) if cursor_col < 0 else cursor_col
    before_cursor = units[:end * 2].decode("utf-16-le", "surrogatepass")
    quoted = _QUOTED.search(before_cursor)
    if quoted:
        return ActiveAtToken(quoted.group(1), quoted.group(2), True)
    plain = _PLAIN.search(before_cursor)
    return ActiveAtToken(plain.group(1), plain.group(2), False) if plain else None

def format_file_mention(candidate: Dict[str, str], preserve_quote: bool = False) -> Optional[str]:
    path = candidate["path"] + ("/" if candidate["kind"] == "directory" else "")
    if re.search(r'[\u0000-\u001f\u007f-\u009f"]', path):
        return None
    quoted = preserve_quote or bool(re.search("[" + _SPACE + "]", path))
    if not quoted:
        return "@" + path
    return '@"' + path + ("" if candidate["kind"] == "directory" else '"')
