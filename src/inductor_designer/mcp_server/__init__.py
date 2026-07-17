"""Pure MCP tool functions over the application/domain layers.

No MCP SDK and no solver SDK imports live here or in ``tools``: every
function takes a :class:`~inductor_designer.mcp_server.tools.ToolContext`
and returns a JSON-able ``dict``, so the eventual MCP server adapter is a
thin transport wrapper around this module.
"""
