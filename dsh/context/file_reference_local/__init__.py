"""Local file-reference service with Agent-owned caches and prompt effects."""
import asyncio
import os

from dsh.context.file_reference import FILE_REFERENCE_PROMPT, FileReferenceService
from dsh.context.file_reference.grammar import active_at_token, format_file_mention
from dsh.context.file_reference_local.search import (
    DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES,
    DEFAULT_FILE_SEARCH_MAX_ENTRIES,
    DEFAULT_FILE_SEARCH_MAX_RESULTS,
    WorkspaceFileSearch,
    validate_config,
)


class LocalFileReferenceService(FileReferenceService):
    """Discover paths without reading or changing any model-visible message."""

    id = "file-reference-local"
    inject = ["agents"]

    def __init__(self, ctx, config=None):
        self.config = validate_config(config or {})
        self.searches = {}
        self.prompt_fibers = {}
        self.prompt_disposals = set()
        self.retired_searches = set()
        super().__init__(ctx)
        for agent in ctx.get("agents").list():
            self.install_prompt(agent)
        ctx.on("agent/created", lambda payload: self.install_prompt(payload["agent"]))
        ctx.on("agent/disposed", lambda payload: self.dispose_agent(payload["agent"]))
        ctx.on("session/event", self.on_session_event)
        ctx.effect(lambda: self.dispose, "file-reference-local: search cache")

    def install_prompt(self, agent):
        if agent in self.prompt_fibers:
            return

        def install(scope):
            scope.get("systemPrompt").section({
                "name": "context:file-reference",
                "order": scope.get("systemPrompt").getSectionOrder("FILE_REFERENCE"),
                "text": lambda _context: FILE_REFERENCE_PROMPT
                if agent.ctx.get("tools").get("read", agent) is not None else "",
            })

        self.prompt_fibers[agent] = agent.ctx.inject(["systemPrompt", "tools"], install)

    def dispose_agent(self, agent):
        search = self.searches.pop(agent, None)
        if search is not None:
            search.dispose()
            self.retired_searches.add(search)
        fiber = self.prompt_fibers.pop(agent, None)
        if fiber is None and search is None:
            return

        async def cleanup():
            try:
                await asyncio.gather(*([fiber.dispose()] if fiber is not None else []) +
                                     ([search.drain()] if search is not None else []))
            except Exception as error:
                self.ctx.logger.warn("file-reference-local: prompt cleanup failed: " + str(error))
            finally:
                self.retired_searches.discard(search)

        task = asyncio.ensure_future(cleanup())
        self.prompt_disposals.add(task)
        task.add_done_callback(self.prompt_disposals.discard)

    def on_session_event(self, session, event):
        if event["type"] != "tool/result":
            return
        agent = self.ctx.get("agents").get(session.id)
        search = self.searches.get(agent)
        if search is not None:
            search.invalidate()

    async def list(self, agent, query, signal):
        search = self.searches.get(agent)
        if search is None:
            search = WorkspaceFileSearch(agent.session.header.cwd or os.getcwd(), self.config)
            self.searches[agent] = search
        return await search.list(query, signal)

    async def dispose(self):
        searches = list(self.searches.values())
        self.searches.clear()
        for search in searches:
            search.dispose()
        fibers = list(self.prompt_fibers.values())
        self.prompt_fibers.clear()
        await asyncio.gather(*(list(self.prompt_disposals) +
                               [fiber.dispose() for fiber in fibers] +
                               [search.drain() for search in searches]))


# Existing Python imports keep resolving while the Loader mounts the service.
FileReferenceLocalPlugin = LocalFileReferenceService

__all__ = ["FileReferenceLocalPlugin", "LocalFileReferenceService", "WorkspaceFileSearch",
           "FILE_REFERENCE_PROMPT", "active_at_token", "format_file_mention",
           "DEFAULT_FILE_SEARCH_MAX_RESULTS", "DEFAULT_FILE_SEARCH_MAX_ENTRIES",
           "DEFAULT_FILE_SEARCH_EXCLUDED_DIRECTORIES"]
