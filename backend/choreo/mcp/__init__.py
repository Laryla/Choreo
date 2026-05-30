# backend/choreo/mcp/__init__.py
from __future__ import annotations
from choreo.mcp.manager import McpManager

_manager: McpManager | None = None


def get_mcp_manager() -> McpManager:
    global _manager
    if _manager is None:
        raise RuntimeError("McpManager not initialized. Call set_mcp_manager() in lifespan.")
    return _manager


def set_mcp_manager(manager: McpManager) -> None:
    global _manager
    _manager = manager


__all__ = ["McpManager", "get_mcp_manager", "set_mcp_manager"]
