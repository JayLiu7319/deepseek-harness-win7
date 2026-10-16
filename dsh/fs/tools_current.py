"""Current file tools; the coordinated profile switch selects these providers."""
from dsh.fs.tool_fs import ToolFsPlugin
from dsh.fs.tool_fs_search import ToolFsSearchPlugin


class CurrentToolFs(ToolFsPlugin):
    current_contract = True


class CurrentToolFsSearch(ToolFsSearchPlugin):
    current_contract = True
