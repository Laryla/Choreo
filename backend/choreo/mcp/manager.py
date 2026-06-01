# backend/choreo/mcp/manager.py
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)


class McpProxyTool:
    """轻量工具代理：存储工具元数据，ainvoke 时通过 McpManager 建新 session 调用。"""

    def __init__(
        self,
        name: str,
        description: str,
        args_schema: dict | None,
        server_name: str,
        manager: "McpManager",
    ) -> None:
        self.name = name
        self.description = description
        self.args_schema = args_schema  # raw JSON Schema dict
        self._server_name = server_name
        self._manager = manager

    async def ainvoke(self, arguments: dict) -> str:
        return await self._manager.call(self._server_name, self.name, arguments)


@asynccontextmanager
async def _open_session(config: dict):
    """按配置打开 MCP ClientSession，yield (session, init_result)，退出自动关闭。"""
    transport = config["transport"]
    if transport == "stdio":
        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args") or [],
            env=config.get("env") or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                yield session, init_result
    elif transport == "sse":
        async with sse_client(config["url"]) as (read, write):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                yield session, init_result
    elif transport in ("http", "streamable-http"):
        async with streamablehttp_client(config["url"]) as (read, write, _):
            async with ClientSession(read, write) as session:
                init_result = await session.initialize()
                yield session, init_result
    else:
        raise ValueError(f"Unsupported MCP transport: {transport}")


def _tools_from_init(init_result) -> list[Tool]:
    """从 initialize 响应的 capabilities.tools 里提取工具（非标准扩展字段）。"""
    try:
        tools_cap = init_result.capabilities.tools if init_result.capabilities else None
        if not tools_cap:
            return []
        # Pydantic v2: 非标准字段存在 model_extra
        extra = getattr(tools_cap, "model_extra", None) or {}
        tools = []
        for val in extra.values():
            if isinstance(val, dict) and "name" in val:
                tools.append(Tool(
                    name=val["name"],
                    description=val.get("description", ""),
                    inputSchema=val.get("inputSchema", {"type": "object", "properties": {}}),
                ))
        return tools
    except Exception as e:
        logger.debug("Could not extract tools from init capabilities: %s", e)
        return []


class McpManager:
    """无状态 MCP 连接管理器。每次工具调用按需打开 session，用完自动关闭。"""

    def __init__(self) -> None:
        self._configs: dict[str, dict] = {}
        self._tool_registry: dict[str, dict[str, McpProxyTool]] = {}
        self._tool_to_server: dict[str, str] = {}

    async def start(self) -> None:
        configs = await self._load_configs()
        if not configs:
            logger.info("No enabled MCP servers, skipping McpManager init.")
            return
        self._configs = configs
        await self._discover_all(list(configs.keys()))

    async def reload(self) -> None:
        self._configs = {}
        self._tool_registry = {}
        self._tool_to_server = {}
        await self.start()

    def get_all_tools_info(self) -> dict[str, list[dict]]:
        return {
            server: [
                {"name": name, "description": tool.description or ""}
                for name, tool in tools.items()
            ]
            for server, tools in self._tool_registry.items()
        }

    async def get_index(self) -> str:
        from choreo.db import SessionLocal, McpServerRow
        from sqlalchemy import select

        if not self._tool_registry:
            return ""

        async with SessionLocal() as session:
            result = await session.execute(select(McpServerRow))
            configs: dict[str, dict] = {
                r.name: r.tools_config or {} for r in result.scalars()
            }

        lines = ["Available MCP Tools (use mcp_call to invoke):"]
        for server_name, tool_dict in self._tool_registry.items():
            server_cfg = configs.get(server_name, {})
            visible = [
                t for name, t in tool_dict.items()
                if server_cfg.get(name, {}).get("approval", "confirm") != "deny"
                and server_cfg.get(name, {}).get("enabled", True)
            ]
            if not visible:
                continue
            lines.append(f"\n{server_name}:")
            for t in visible:
                desc = (t.description or "").split("\n")[0][:100]
                sig = self._tool_signature(t)
                lines.append(f"  {sig}: {desc}")

        return "\n".join(lines) if len(lines) > 1 else ""

    async def get_schema(self, server: str, tool: str) -> dict | None:
        from choreo.db import SessionLocal, McpServerRow

        server_tools = self._tool_registry.get(server)
        if not server_tools:
            return None
        t = server_tools.get(tool)
        if not t or not t.args_schema:
            return None

        try:
            async with SessionLocal() as session:
                row = await session.get(McpServerRow, server)
                cfg = (row.tools_config or {}).get(tool, {}) if row else {}
                if cfg.get("approval") == "deny" or not cfg.get("enabled", True):
                    return None
        except Exception as e:
            logger.warning("DB error checking schema access for %s/%s: %s", server, tool, e)
            return None

        return t.args_schema

    async def call(self, server: str, tool: str, arguments: dict) -> str:
        approval = await _get_approval(server, tool)
        if approval == "deny":
            return f"Tool '{server}/{tool}' is blocked by policy."

        server_tools = self._tool_registry.get(server)
        if server_tools is None:
            return f"MCP server '{server}' is not connected or has no tools."

        if tool not in server_tools:
            available = ", ".join(server_tools.keys())
            return f"Tool '{tool}' not found in '{server}'. Available: {available}"

        config = self._configs.get(server)
        if not config:
            return f"No config found for MCP server '{server}'."

        try:
            async with _open_session(config) as (session, _):
                result = await session.call_tool(tool, arguments)
                parts = []
                for block in result.content:
                    if isinstance(block, TextContent):
                        parts.append(block.text)
                    else:
                        parts.append(str(block))
                return "\n".join(parts) if parts else ""
        except Exception as e:
            return f"MCP tool call failed ({server}/{tool}): {e}"

    async def _load_configs(self) -> dict:
        from choreo.db import SessionLocal, McpServerRow
        from sqlalchemy import select

        async with SessionLocal() as session:
            result = await session.execute(
                select(McpServerRow).where(McpServerRow.enabled == True)
            )
            servers = list(result.scalars())

        configs = {}
        for s in servers:
            if s.transport == "stdio":
                if not s.command:
                    logger.warning("MCP server '%s' has no command, skipping.", s.name)
                    continue
                configs[s.name] = {
                    "transport": "stdio",
                    "command": s.command,
                    "args": s.args or [],
                    "env": s.env or {},
                }
            elif s.transport in ("sse", "http", "streamable-http"):
                if not s.url:
                    logger.warning("MCP server '%s' has no url, skipping.", s.name)
                    continue
                configs[s.name] = {
                    "transport": s.transport,
                    "url": s.url,
                }
        return configs

    async def _discover_all(self, server_names: list[str]) -> None:
        tasks = [self._discover_one(name) for name in server_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(server_names, results):
            if isinstance(result, Exception):
                logger.warning("Failed to discover tools for '%s': %s", name, result)

    async def _discover_one(self, server_name: str) -> None:
        config = self._configs[server_name]

        async def _fetch_tools():
            async with _open_session(config) as (session, init_result):
                try:
                    # 先尝试标准 list_tools（10s 超时）
                    result = await asyncio.wait_for(session.list_tools(), timeout=10.0)
                    return result.tools
                except asyncio.TimeoutError:
                    # 服务器不走标准 list_tools，从 initialize 返回的 capabilities 提取
                    logger.info(
                        "list_tools timed out for '%s', extracting tools from init capabilities.",
                        server_name,
                    )
                    return _tools_from_init(init_result)

        try:
            mcp_tools = await asyncio.wait_for(_fetch_tools(), timeout=20.0)
        except asyncio.TimeoutError:
            logger.warning("Tool discovery for '%s' timed out (20s).", server_name)
            return

        proxy_tools = [
            McpProxyTool(
                name=t.name,
                description=t.description or "",
                args_schema=t.inputSchema if isinstance(t.inputSchema, dict) else None,
                server_name=server_name,
                manager=self,
            )
            for t in mcp_tools
        ]

        self._tool_registry[server_name] = {t.name: t for t in proxy_tools}
        for t in proxy_tools:
            if t.name in self._tool_to_server:
                logger.warning(
                    "Tool name collision: '%s' in both '%s' and '%s'.",
                    t.name, self._tool_to_server[t.name], server_name,
                )
            self._tool_to_server[t.name] = server_name

        logger.info("MCP server '%s': discovered %d tools.", server_name, len(proxy_tools))
        await self._sync_to_db(server_name, proxy_tools)

    async def _sync_to_db(self, server_name: str, tools: list[McpProxyTool]) -> None:
        from choreo.db import SessionLocal, McpServerRow

        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server_name)
            if not row:
                return
            existing = row.tools_config or {}
            new_config = {}
            for t in tools:
                if t.name in existing:
                    new_config[t.name] = existing[t.name]
                else:
                    new_config[t.name] = {"approval": "auto", "enabled": True}
            row.tools_config = new_config
            await session.commit()

    @staticmethod
    def _json_type_hint(prop: dict) -> str:
        t = prop.get("type", "")
        if t == "string":
            if "enum" in prop:
                return "|".join(f'"{v}"' for v in prop["enum"])
            return "str"
        if t == "integer":
            return "int"
        if t == "number":
            return "float"
        if t == "boolean":
            return "bool"
        if t == "array":
            inner = McpManager._json_type_hint(prop.get("items", {}))
            return f"list[{inner}]"
        if t == "object":
            return "dict"
        for key in ("anyOf", "oneOf"):
            variants = prop.get(key, [])
            non_null = [v for v in variants if v.get("type") != "null"]
            if non_null:
                return McpManager._json_type_hint(non_null[0])
        return "any"

    def _tool_signature(self, t: McpProxyTool) -> str:
        try:
            schema = t.args_schema or {}
            required = set(schema.get("required", []))
            params = []
            for name, prop in schema.get("properties", {}).items():
                type_hint = self._json_type_hint(prop)
                if name in required:
                    params.append(f"{name}: {type_hint}")
                else:
                    params.append(f"{name}?: {type_hint}")
            return f"{t.name}({', '.join(params)})"
        except Exception:
            return t.name


async def _get_approval(server: str, tool: str) -> str:
    from choreo.db import SessionLocal, McpServerRow
    try:
        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server)
            if row and row.tools_config:
                return row.tools_config.get(tool, {}).get("approval", "confirm")
    except Exception as e:
        logger.warning("Failed to read approval config for %s/%s: %s", server, tool, e)
    return "confirm"
