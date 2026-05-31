# backend/choreo/mcp/manager.py
from __future__ import annotations
import asyncio
import logging
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class McpManager:
    """无状态 MCP 连接管理器。

    MultiServerMCPClient 默认无状态——每次工具调用自动创建 session 并清理，
    无需手动管理连接生命周期。
    """

    def __init__(self) -> None:
        self._client: MultiServerMCPClient | None = None
        # {server_name: {tool_name: BaseTool}}
        self._tool_registry: dict[str, dict[str, BaseTool]] = {}
        # {tool_name: server_name}，供 deny_interceptor 查 server
        self._tool_to_server: dict[str, str] = {}

    async def start(self) -> None:
        """lifespan 启动时调用：构建 client，发现工具，同步 DB。"""
        configs = await self._load_configs()
        if not configs:
            logger.info("No enabled MCP servers, skipping McpManager init.")
            return
        self._client = MultiServerMCPClient(
            configs,
            tool_interceptors=[self._make_deny_interceptor()],
        )
        await self._discover_all(list(configs.keys()))

    async def reload(self) -> None:
        """重新加载：从 DB 重读配置，重建 client 和工具注册表。"""
        self._client = None
        self._tool_registry = {}
        self._tool_to_server = {}
        await self.start()

    def get_all_tools_info(self) -> dict[str, list[dict]]:
        """返回已发现的工具信息，供 /api/mcp/tools 端点使用。"""
        return {
            server: [
                {"name": name, "description": tool.description or ""}
                for name, tool in tools.items()
            ]
            for server, tools in self._tool_registry.items()
        }

    async def get_index(self) -> str:
        """生成紧凑工具目录文字，过滤 approval=deny 和 enabled=false 的工具。"""
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
        """返回指定工具的完整 JSON schema，过滤 deny/disabled 工具，供 mcp_describe 使用。"""
        from choreo.db import SessionLocal, McpServerRow

        server_tools = self._tool_registry.get(server)
        if not server_tools:
            return None
        t = server_tools.get(tool)
        if not t or not t.args_schema:
            return None

        # 过滤 deny/disabled，避免暴露被 block 工具的 schema
        try:
            async with SessionLocal() as session:
                row = await session.get(McpServerRow, server)
                cfg = (row.tools_config or {}).get(tool, {}) if row else {}
                if cfg.get("approval") == "deny" or not cfg.get("enabled", True):
                    return None
        except Exception as e:
            logger.warning("DB error checking schema access for %s/%s: %s", server, tool, e)
            return None  # fail-closed: don't expose schema on DB error

        try:
            if isinstance(t.args_schema, dict):
                return t.args_schema  # langchain-mcp-adapters 直接存 JSON schema dict
            try:
                return t.args_schema.model_json_schema()  # pydantic v2
            except AttributeError:
                return t.args_schema.schema()             # pydantic v1 fallback
        except Exception:
            return None

    async def call(self, server: str, tool: str, arguments: dict) -> str:
        """通过注册表找到工具并调用，结果经过 deny_interceptor。"""
        # Enforce deny policy before reaching ainvoke
        approval = await _get_approval(server, tool)
        if approval == "deny":
            return f"Tool '{server}/{tool}' is blocked by policy."

        server_tools = self._tool_registry.get(server)
        if server_tools is None:
            return f"MCP server '{server}' is not connected or has no tools."

        target = server_tools.get(tool)
        if target is None:
            available = ", ".join(server_tools.keys())
            return f"Tool '{tool}' not found in '{server}'. Available: {available}"

        try:
            result = await target.ainvoke(arguments)
            return str(result)
        except Exception as e:
            return f"MCP tool call failed ({server}/{tool}): {e}"

    async def _load_configs(self) -> dict:
        """从 DB 读取 enabled MCP servers，构建 MultiServerMCPClient 配置。"""
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
            elif s.transport in ("sse", "http"):
                if not s.url:
                    logger.warning("MCP server '%s' has no url, skipping.", s.name)
                    continue
                configs[s.name] = {
                    "transport": s.transport,
                    "url": s.url,
                }
        return configs

    async def _discover_all(self, server_names: list[str]) -> None:
        """并发发现所有 server 的工具，超时 15s 跳过。"""
        tasks = [self._discover_one(name) for name in server_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for name, result in zip(server_names, results):
            if isinstance(result, Exception):
                logger.warning("Failed to discover tools for '%s': %s", name, result)

    async def _discover_one(self, server_name: str) -> None:
        try:
            tools: list[BaseTool] = await asyncio.wait_for(
                self._client.get_tools(server_name=server_name),
                timeout=15.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Tool discovery for '%s' timed out (15s).", server_name)
            return

        self._tool_registry[server_name] = {t.name: t for t in tools}
        for t in tools:
            if t.name in self._tool_to_server:
                logger.warning(
                    "Tool name collision: '%s' exists in both '%s' and '%s'. "
                    "deny_interceptor will use '%s'.",
                    t.name, self._tool_to_server[t.name], server_name, server_name,
                )
            self._tool_to_server[t.name] = server_name

        logger.info("MCP server '%s': discovered %d tools.", server_name, len(tools))
        await self._sync_to_db(server_name, tools)

    async def _sync_to_db(self, server_name: str, tools: list[BaseTool]) -> None:
        """将发现的工具同步到 DB tools_config，保留已有用户配置。"""
        from choreo.db import SessionLocal, McpServerRow

        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server_name)
            if not row:
                return
            existing = row.tools_config or {}
            new_config = {}
            for t in tools:
                if t.name in existing:
                    new_config[t.name] = existing[t.name]  # 保留用户配置
                else:
                    new_config[t.name] = {"approval": "confirm", "enabled": True}
            row.tools_config = new_config
            await session.commit()

    @staticmethod
    def _json_type_hint(prop: dict) -> str:
        """Map a JSON Schema property dict to a compact type string."""
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
        # anyOf / oneOf fallback
        for key in ("anyOf", "oneOf"):
            variants = prop.get(key, [])
            non_null = [v for v in variants if v.get("type") != "null"]
            if non_null:
                return McpManager._json_type_hint(non_null[0])
        return "any"

    def _tool_signature(self, t: BaseTool) -> str:
        """Build 'tool_name(param: type, optional?: type)' from tool schema."""
        try:
            if isinstance(t.args_schema, dict):
                schema = t.args_schema  # langchain-mcp-adapters 直接存 JSON schema dict
            elif t.args_schema:
                try:
                    schema = t.args_schema.model_json_schema()  # pydantic v2
                except AttributeError:
                    schema = t.args_schema.schema()             # pydantic v1 fallback
            else:
                schema = {}
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

    def _make_deny_interceptor(self):
        """返回在 MCP 层拦截 deny 工具的 interceptor 函数。"""
        manager = self

        async def deny_interceptor(request, handler):
            tool_name = request.name
            server_name = manager._tool_to_server.get(tool_name, "")
            if server_name:
                approval = await _get_approval(server_name, tool_name)
                if approval == "deny":
                    from langchain_core.messages import ToolMessage
                    tool_call_id = getattr(request.runtime, "tool_call_id", "") or ""
                    return ToolMessage(
                        content=f"Tool '{server_name}/{tool_name}' is blocked by policy.",
                        tool_call_id=tool_call_id,
                    )
            return await handler(request)

        return deny_interceptor


async def _get_approval(server: str, tool: str) -> str:
    """从 DB 读取工具的 approval 配置，默认 confirm。"""
    from choreo.db import SessionLocal, McpServerRow
    try:
        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server)
            if row and row.tools_config:
                return row.tools_config.get(tool, {}).get("approval", "confirm")
    except Exception as e:
        logger.warning("Failed to read approval config for %s/%s: %s", server, tool, e)
    return "confirm"
