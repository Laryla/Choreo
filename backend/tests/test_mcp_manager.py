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


@pytest.mark.asyncio
async def test_sync_to_db_preserves_user_config(monkeypatch):
    """_sync_to_db must keep existing user approval/enabled config."""
    from unittest.mock import AsyncMock, MagicMock
    from choreo.mcp.manager import McpManager

    manager = McpManager()

    # Fake DB row with existing user config
    existing_config = {"old_tool": {"approval": "auto", "enabled": True}}
    mock_row = MagicMock()
    mock_row.tools_config = existing_config

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_row)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_session_local = MagicMock(return_value=mock_session)
    monkeypatch.setattr("choreo.db.SessionLocal", mock_session_local)

    # Sync with the same tool
    fake_tool = MagicMock()
    fake_tool.name = "old_tool"
    await manager._sync_to_db("myserver", [fake_tool])

    # User config must be preserved
    final_config = mock_row.tools_config
    assert final_config["old_tool"]["approval"] == "auto"


@pytest.mark.asyncio
async def test_get_index_filters_deny_tools(monkeypatch):
    """get_index must exclude tools with approval=deny or enabled=False."""
    from unittest.mock import AsyncMock, MagicMock
    from choreo.mcp.manager import McpManager

    manager = McpManager()

    # Populate registry with two tools
    mock_allowed = MagicMock()
    mock_allowed.name = "allowed_tool"
    mock_allowed.description = "An allowed tool"
    mock_allowed.args_schema = None

    mock_denied = MagicMock()
    mock_denied.name = "denied_tool"
    mock_denied.description = "A denied tool"
    mock_denied.args_schema = None

    manager._tool_registry["myserver"] = {
        "allowed_tool": mock_allowed,
        "denied_tool": mock_denied,
    }

    # DB config: allowed_tool=auto, denied_tool=deny
    mock_row = MagicMock()
    mock_row.name = "myserver"
    mock_row.tools_config = {
        "allowed_tool": {"approval": "auto", "enabled": True},
        "denied_tool": {"approval": "deny", "enabled": True},
    }

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=[mock_row])))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    monkeypatch.setattr("choreo.db.SessionLocal", MagicMock(return_value=mock_session))

    index = await manager.get_index()
    assert "allowed_tool" in index
    assert "denied_tool" not in index
