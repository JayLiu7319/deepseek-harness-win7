"""Current MCP client rejects pagination cycles before registry replacement."""
from dsh.mcp.client import McpClientPlugin
from dsh.mcp.connection import McpConnection
from dsh.mcp.tools import sync_tools as previous_sync


async def sync_tools(client, ctx, opts, previous):
    return await previous_sync(client, ctx, dict(opts, currentContract=True), previous)


class CurrentMcpConnection(McpConnection):
    current_contract = True


class CurrentMcpClient(McpClientPlugin):
    connection_class = CurrentMcpConnection
