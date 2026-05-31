# backend/choreo/mcp/builtin.py
import logging
import sys
import time

logger = logging.getLogger(__name__)

# Bridge script embedded inline — 把 HTTP MCP 端点桥接成 stdio
# 用 python -c 执行，sys.argv[1] 接收 URL 参数
_BRIDGE_CODE = r"""
import json, sys
import httpx

def main(url):
    with httpx.Client(
        timeout=30,
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    ) as client:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            is_request = "id" in msg
            try:
                resp = client.post(url, json=msg)
                if not is_request:
                    continue
                text = resp.text.strip()
                if not text:
                    continue
                if text.startswith("event:") or text.startswith("data:"):
                    for sse_line in text.splitlines():
                        if sse_line.startswith("data:"):
                            data = sse_line[5:].strip()
                            if data:
                                sys.stdout.write(data + "\n")
                                sys.stdout.flush()
                elif text:
                    sys.stdout.write(text + "\n")
                    sys.stdout.flush()
            except Exception as e:
                if not is_request:
                    continue
                sys.stdout.write(json.dumps({"jsonrpc":"2.0","id":msg.get("id"),"error":{"code":-32603,"message":str(e)}}) + "\n")
                sys.stdout.flush()

main(sys.argv[1])
"""

_BUILTIN_SERVERS = [
    {
        "name": "langchain-docs",
        "transport": "stdio",
        "command": sys.executable,
        "args": ["-c", _BRIDGE_CODE, "https://docs.langchain.com/mcp"],
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
