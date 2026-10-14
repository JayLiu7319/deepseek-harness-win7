import asyncio
import os
import stat
from typing import Any, Dict, List, Optional, Set

DEFAULT_FILE_SEARCH_MAX_RESULTS = 20
DEFAULT_FILE_SEARCH_MAX_ENTRIES = 50_000
DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES = [
    ".git", "node_modules", "dist", "build", "out", "coverage", "target",
    ".next", ".nuxt", ".turbo", ".venv", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".gradle",
]

from dsh.core.abort import AbortController, NEVER_ABORTED
from dsh.cordis.errors import ThrownValueError


def _error_reason(reason, fallback):
    if isinstance(reason, BaseException) and not isinstance(reason, ThrownValueError):
        return reason
    error = RuntimeError(fallback)
    error.cause = reason.value if isinstance(reason, ThrownValueError) else reason
    return error


async def _wait_for_index(operation, signal):
    """Borrow one traversal without transferring cancellation to its owner."""
    if signal.aborted:
        raise _error_reason(signal.reason, "file search aborted")
    view = asyncio.get_running_loop().create_future()

    def aborted(_event):
        if not view.done():
            view.set_exception(_error_reason(signal.reason, "file search aborted"))

    def settled(job):
        signal.removeEventListener("abort", aborted)
        error = asyncio.CancelledError() if job.cancelled() else job.exception()
        if view.done():
            return
        if error is None:
            view.set_result(job.result())
        else:
            view.set_exception(_error_reason(error, "file search index failed"))

    signal.addEventListener("abort", aborted, {"once": True})
    operation.add_done_callback(settled)
    try:
        return await view
    finally:
        signal.removeEventListener("abort", aborted)


def validate_config(config):
    result = dict(maxResults=config.get("maxResults", DEFAULT_FILE_SEARCH_MAX_RESULTS),
                  maxEntries=config.get("maxEntries", DEFAULT_FILE_SEARCH_MAX_ENTRIES),
                  excludedDirectories=config.get("excludedDirectories", DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES))
    for key in ("maxResults", "maxEntries"):
        if (type(result[key]) not in (int, float) or not 1 <= result[key] <= 9007199254740991
                or int(result[key]) != result[key]):
            raise ValueError("file search " + key + " must be a positive safe integer")
        result[key] = int(result[key])
    excluded = result["excludedDirectories"]
    if not isinstance(excluded, (list, tuple)) or any(
            not isinstance(name, str) or not name or "/" in name or "\\" in name for name in excluded):
        raise ValueError("file search excludedDirectories entries must be non-empty directory basenames")
    result["excludedDirectories"] = list(excluded)
    return result


def _text_key(text):
    """JavaScript code-unit ordering, independent of host locale."""
    return text.encode("utf-16-be", errors="surrogatepass")


def subsequence_score(target: str, query: str) -> Optional[int]:
    # String.indexOf reports UTF-16 positions, while JS for-of iterates query
    # code points. Preserve its +1 cursor advance even for a surrogate pair.
    encoded = _text_key(target)
    target_index = 0
    gap = 0
    for char in query:
        found = encoded.find(_text_key(char), target_index * 2)
        while found >= 0 and found % 2:
            found = encoded.find(_text_key(char), found + 1)
        if found < 0:
            return None
        found //= 2
        gap += found - target_index
        target_index = found + 1
    return max(0, 100 - gap)


def score_candidate(candidate: Dict[str, str], query: str) -> Optional[int]:
    if not query:
        return 0
    path = candidate["path"].lower()
    last_slash = path.rfind("/")
    name = path if last_slash < 0 else path[last_slash + 1:]
    needle = query.lower()
    directory_bonus = 25 if candidate.get("kind") == "directory" else 0

    if name == needle:
        return 1000 + directory_bonus
    if name.startswith(needle):
        return 900 + directory_bonus
    if needle in name:
        return 700 + directory_bonus
    if needle in path:
        return 500 + directory_bonus

    subseq = subsequence_score(path, needle)
    if subseq is not None:
        return 300 + subseq + directory_bonus
    return None


def rank_candidates(
    candidates: List[Dict[str, str]], query: str, limit: int
) -> List[Dict[str, str]]:
    ranked = []
    for candidate in candidates:
        score = score_candidate(candidate, query)
        if score is not None:
            ranked.append((score, candidate))

    def sort_key(item: Any) -> Any:
        score, candidate = item
        kind_rank = 0 if candidate.get("kind") == "directory" else 1
        path_len = len(_text_key(candidate["path"])) // 2 if query else 0
        return (-score, kind_rank, path_len, _text_key(candidate["path"]))

    ranked.sort(key=sort_key)
    return [item[1] for item in ranked[:limit]]


def visible_for_global_query(path: str, query: str) -> bool:
    if query.startswith(".") or "/." in query:
        return True
    return not any(segment.startswith(".") for segment in path.split("/"))


def _directory_entries(absolute):
    rows = []
    with os.scandir(absolute) as entries:
        for entry in entries:
            try:
                status = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISLNK(status.st_mode) or getattr(status, "st_file_attributes", 0) & 0x400:
                continue
            if stat.S_ISDIR(status.st_mode):
                rows.append((entry.name, "directory"))
            elif stat.S_ISREG(status.st_mode):
                rows.append((entry.name, "file"))
    return sorted(rows, key=lambda row: _text_key(row[0]))


class WorkspaceFileSearch:
    """Shared bounded index; caller cancellation never cancels another query."""

    def __init__(self, root: str, config: Optional[Dict[str, Any]] = None):
        self.root = os.path.abspath(root)
        self.config = validate_config(config or {})
        self.max_results = self.config["maxResults"]
        self.max_entries = self.config["maxEntries"]
        self.excluded_directories = set(self.config["excludedDirectories"])
        self._settled = None
        self._generation = None
        self._controller = None
        self._invalidations = 0
        self._disposed = False
        self._jobs = set()

    def invalidate(self) -> None:
        self._invalidations += 1

    def dispose(self) -> None:
        if self._disposed:
            return
        self._disposed = True
        if self._controller is not None:
            self._controller.abort(RuntimeError("file search index disposed"))
        self._generation = self._controller = self._settled = None

    async def drain(self):
        if self._jobs:
            await asyncio.gather(*list(self._jobs), return_exceptions=True)

    async def list(self, raw_query: str = "", signal: Any = None) -> List[Dict[str, str]]:
        signal = signal if signal is not None else NEVER_ABORTED
        signal.throw_if_aborted()
        if self._disposed:
            return []
        query = raw_query.replace(chr(92), "/")
        slash = query.rfind("/")
        if not query or slash >= 0:
            directory = "" if slash < 0 else query[:slash + 1]
            fragment = "" if slash < 0 else query[slash + 1:]
            return await self.list_directory(directory, fragment, signal)
        indexed = await self.index_for(signal)
        filtered = [row for row in indexed if visible_for_global_query(row["path"], query)]
        return rank_candidates(filtered, query, self.max_results)

    async def list_candidates(self, query: str = "") -> List[Dict[str, str]]:
        return await self.list(query)

    async def index_for(self, signal):
        if self._settled is None:
            return await _wait_for_index(self.ensure_index(), signal)
        entries, started_at = self._settled
        if started_at < self._invalidations:
            self.ensure_index()
        return entries

    def ensure_index(self):
        if self._generation is not None:
            return self._generation
        self._controller = AbortController()
        started_at = self._invalidations
        controller = self._controller

        async def build():
            try:
                entries = await self.scan_workspace(controller.signal)
                if not self._disposed:
                    self._settled = (entries, started_at)
                return entries
            finally:
                if self._controller is controller:
                    self._generation = self._controller = None

        task = asyncio.ensure_future(build())
        self._generation = task
        self._jobs.add(task)

        def observe(job):
            self._jobs.discard(job)
            if not job.cancelled():
                job.exception()  # Background refresh keeps the previous settled entries.

        task.add_done_callback(observe)
        return task

    async def read_directory(self, absolute, signal, root=False):
        signal.throw_if_aborted()
        try:
            entries = await asyncio.get_running_loop().run_in_executor(None, _directory_entries, absolute)
        except OSError:
            signal.throw_if_aborted()
            if root:
                raise
            return []
        signal.throw_if_aborted()
        return entries

    async def scan_workspace(self, signal) -> List[Dict[str, str]]:
        indexed = []
        directories = [(self.root, "")]
        cursor = 0
        while cursor < len(directories) and len(indexed) < self.max_entries:
            signal.throw_if_aborted()
            absolute, relative = directories[cursor]
            entries = await self.read_directory(absolute, signal, root=cursor == 0)
            cursor += 1
            for name, kind in entries:
                signal.throw_if_aborted()
                path = name if not relative else relative + "/" + name
                if kind == "directory":
                    if name in self.excluded_directories:
                        continue
                    directories.append((os.path.join(absolute, name), path))
                indexed.append({"path": path, "kind": kind})
                if len(indexed) >= self.max_entries:
                    break
        return indexed

    async def resolve_directory(self, display_directory, signal):
        absolute = os.path.abspath(os.path.join(self.root, display_directory or "."))
        try:
            relative = os.path.relpath(absolute, self.root)
        except ValueError:
            return None
        if relative == ".." or relative.startswith(".." + os.sep) or os.path.isabs(relative):
            return None
        current = self.root
        for segment in relative.split(os.sep):
            if segment in ("", "."):
                continue
            signal.throw_if_aborted()
            current = os.path.join(current, segment)
            try:
                status = await asyncio.get_running_loop().run_in_executor(None, os.lstat, current)
            except (OSError, ValueError):
                signal.throw_if_aborted()
                return None
            signal.throw_if_aborted()
            if (stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode)
                    or getattr(status, "st_file_attributes", 0) & 0x400):
                return None
        return absolute

    async def list_directory(self, display_directory, fragment, signal=NEVER_ABORTED):
        if any(segment in self.excluded_directories for segment in display_directory.split("/")):
            return []
        absolute = await self.resolve_directory(display_directory, signal)
        if absolute is None:
            return []
        entries = await self.read_directory(absolute, signal)
        candidates = []
        for name, kind in entries:
            if name.startswith(".") and not fragment.startswith("."):
                continue
            if kind == "directory" and name in self.excluded_directories:
                continue
            candidates.append({"path": display_directory + name, "kind": kind})
        return rank_candidates(candidates, fragment, self.max_results)
