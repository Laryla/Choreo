# backend/tests/test_mcp_manager.py
import pytest
from choreo.mcp.manager import McpManager


@pytest.mark.asyncio
async def test_manager_starts_empty():
    manager = McpManager()
    assert manager.get_all_tools_info() == {}
    assert manager._tool_registry == {}


@pytest.mark.asyncio
async def test_manager_reload_is_safe_when_no_servers(monkeypatch):
    manager = McpManager()
    # Stub out DB call so test works without a real database
    async def _no_servers(self):
        return {}
    monkeypatch.setattr(McpManager, "_load_configs", _no_servers)
    await manager.reload()   # _load_configs 返回空，不应报错
    assert manager._client is None


@pytest.mark.asyncio
async def test_call_returns_error_for_unknown_server():
    manager = McpManager()
    result = await manager.call("nonexistent", "some_tool", {})
    assert "not found" in result.lower() or "not connected" in result.lower()


@pytest.mark.asyncio
async def test_get_index_empty_when_no_registry():
    manager = McpManager()
    index = await manager.get_index()
    assert index == ""


@pytest.mark.asyncio
async def test_call_unknown_server():
    manager = McpManager()
    result = await manager.call("ghost", "some_tool", {})
    assert "ghost" in result


@pytest.mark.asyncio
async def test_call_unknown_tool():
    manager = McpManager()
    manager._tool_registry["myserver"] = {}  # empty tools
    result = await manager.call("myserver", "nonexistent", {})
    assert "not found" in result
