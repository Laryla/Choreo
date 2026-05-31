# backend/choreo/mcp/builtin.py
import logging
import time

logger = logging.getLogger(__name__)

_BUILTIN_SERVERS = [
    {
        "name": "langchain-docs",
        "transport": "http",
        "url": "https://docs.langchain.com/mcp",
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
        await session.commit()
