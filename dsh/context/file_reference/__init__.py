"""Agent-scoped discovery of path-only file references."""
from dsh.cordis.service import Service
from dsh.context.file_reference.grammar import ActiveAtToken, active_at_token, format_file_mention

FILE_REFERENCE_PROMPT = (
    "Tokens prefixed with @ are workspace paths the user explicitly referenced, "
    "relative to the workspace root. A trailing slash marks a directory: "
    "list it when its contents matter. Anything else is a file: use the read tool "
    "when its contents are needed, and do not claim to have inspected it before "
    'reading. @"..." quotes a path containing spaces.'
)


class FileReferenceService(Service):
    """Cancellable file and directory candidates for an Agent's session cwd."""

    def __init__(self, ctx):
        super().__init__(ctx, "fileReferences")

    async def list(self, agent, query, signal):
        raise NotImplementedError
