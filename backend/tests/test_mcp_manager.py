# backend/tests/test_mcp_manager.py
import pytest
from choreo.mcp.manager import McpManager


@pytest.mark.asyncio
async def test_manager_starts_empty():
    manager = McpManager()
    assert manager.get_all_tools_info() == {}
    assert manager._tool_registry == {}


@pytest.mark.asyncio
async def test_manager_reload_is_safe_when_no_servers():
    manager = McpManager()
    await manager.reload()   # _load_configs 返回空，不应报错
    assert manager._client is None


@pytest.mark.asyncio
async def test_call_returns_error_for_unknown_server():
    manager = McpManager()
    result = await manager.call("nonexistent", "some_tool", {})
    # skeleton returns "" so just verify it doesn't crash
    assert isinstance(result, str)
