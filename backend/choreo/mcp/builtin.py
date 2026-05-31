# backend/choreo/mcp/builtin.py
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

BUILTIN_SERVERS = [
    {
        "name": "langchain-docs",
        "transport": "http",  # Streamable HTTP（非旧版 SSE）
        "url": "https://docs.langchain.com/mcp",
    },
]


async def seed_builtin_mcp_servers() -> None:
    """将内置 MCP 服务器 seed 进 DB（幂等，已存在则跳过）。"""
    from choreo.db import SessionLocal, McpServerRow

    async with SessionLocal() as session:
        for s in BUILTIN_SERVERS:
            existing = await session.get(McpServerRow, s["name"])
            if existing is not None:
                continue
            row = McpServerRow(
                name=s["name"],
                transport=s["transport"],
                url=s.get("url"),
                command=s.get("command"),
                args=s.get("args", []),
                env=s.get("env", {}),
                enabled=True,
                tools_config={},
            )
            session.add(row)
            logger.info("Seeded built-in MCP server: %s", s["name"])
        await session.commit()
