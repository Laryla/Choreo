# backend/choreo/mcp/builtin.py
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_BRIDGE_SCRIPT = str(Path(__file__).parent / "http_stdio_bridge.py")

_BUILTIN_SERVERS = [
    {
        "name": "langchain-docs",
        "transport": "stdio",
        "command": sys.executable,
        "args": [_BRIDGE_SCRIPT, "https://docs.langchain.com/mcp"],
        "enabled": True,
    },
]


async def seed_builtin_mcp_servers() -> None:
    """预置内置 MCP servers（幂等，已存在则跳过）。"""
    from choreo.db import SessionLocal, McpServerRow

    async with SessionLocal() as session:
        for server in _BUILTIN_SERVERS:
            existing = await session.get(McpServerRow, server["name"])
            if existing is None:
                row = McpServerRow(
                    name=server["name"],
                    transport=server["transport"],
                    url=server.get("url"),
                    command=server.get("command"),
                    args=server.get("args", []),
                    env=server.get("env", {}),
                    enabled=server["enabled"],
                    created_at=int(time.time()),
                )
                session.add(row)
                logger.info("Seeded built-in MCP server: %s", server["name"])
            else:
                # 迁移旧记录到正确的 transport 配置
                changed = False
                if existing.transport != server["transport"]:
                    existing.transport = server["transport"]
                    changed = True
                if server.get("command") and existing.command != server["command"]:
                    existing.command = server["command"]
                    changed = True
                if server.get("args") and existing.args != server["args"]:
                    existing.args = server["args"]
                    changed = True
                if server.get("url") is None and existing.url is not None:
                    existing.url = None
                    changed = True
                if changed:
                    logger.info("Migrated built-in MCP server config: %s", server["name"])
        await session.commit()
