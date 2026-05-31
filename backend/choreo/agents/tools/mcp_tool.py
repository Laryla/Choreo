import json
from langchain_core.tools import tool
from choreo.mcp import get_mcp_manager


@tool
async def mcp_call(server: str, tool: str, arguments: dict) -> str:
    """Call a tool on an MCP server.

    Use this when you see tools listed under "Available MCP Tools" in the
    system prompt. Pass the server name, tool name, and arguments exactly
    as shown in the signature. If unsure about parameter types or constraints,
    call mcp_describe first.

    Args:
        server: MCP server name (e.g. "github", "postgres")
        tool: Tool name to call (e.g. "create_issue", "query")
        arguments: Arguments dict for the tool

    Returns:
        Tool execution result as string.
    """
    return await get_mcp_manager().call(server, tool, arguments)


@tool
async def mcp_call_auto(server: str, tool: str, arguments: dict) -> str:
    """Internal: auto-approved variant of mcp_call, bypasses HITL confirmation."""
    return await get_mcp_manager().call(server, tool, arguments)


@tool
async def mcp_describe(server: str, tool: str) -> str:
    """Get the full JSON schema for an MCP tool's parameters.

    Use this before calling mcp_call when you are unsure about parameter
    types, constraints, or enum values. Returns the complete input schema
    so you can construct the arguments correctly.

    Args:
        server: MCP server name (e.g. "github", "postgres")
        tool: Tool name (e.g. "create_issue", "query")

    Returns:
        Pretty-printed JSON schema, or an error message if not found.
    """
    try:
        manager = get_mcp_manager()
    except RuntimeError:
        return "MCP manager not initialized."
    schema = await manager.get_schema(server, tool)
    if schema is None:
        return f"No schema found for '{server}/{tool}'. It may not exist or is blocked."
    return json.dumps(schema, indent=2, ensure_ascii=False)
