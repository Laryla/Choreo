# backend/choreo/mcp/manager.py
from __future__ import annotations
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
        """生成紧凑工具目录文字（过滤 deny/disabled 工具）。"""
        return ""  # Task 3 实现

    async def get_schema(self, server: str, tool: str) -> dict | None:
        """返回指定工具的完整 JSON schema。"""
        return None  # Task 3 实现

    async def call(self, server: str, tool: str, arguments: dict) -> str:
        """代理调用指定 server 的工具。"""
        return ""  # Task 3 实现

    async def _load_configs(self) -> dict:
        return {}  # Task 3 实现

    async def _discover_all(self, server_names: list[str]) -> None:
        pass  # Task 3 实现

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
