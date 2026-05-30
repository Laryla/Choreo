# MCP 工具渐进式注册机制 实现计划（v2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 实现 MCP 工具的渐进式注册——Agent 工具列表只注册一个 `mcp_call` 代理工具，通过 `McpContextMiddleware` 动态注入紧凑工具目录文字，通过 `McpApprovalMiddleware` 处理 `confirm` 审批（HITL），`deny` 由 MCP 层的 `tool_interceptors` 处理。

**架构：** `MultiServerMCPClient` 无状态模式（官方推荐）——不需要管理连接生命周期，每次工具调用自动创建 session 并清理。McpManager 在 lifespan 启动时发现工具并同步到 DB。

**关键设计决策（来自官方文档）：**
- `MultiServerMCPClient` 默认无状态，无需 `__aenter__/__aexit__`
- `deny` 通过 `tool_interceptors` 在 MCP 层拦截
- `confirm` 通过 `McpApprovalMiddleware` 在 LangGraph 层触发 HITL `interrupt()`
- `auto` 两层都直接放行

**技术栈：** FastAPI lifespan · LangGraph AgentMiddleware · langchain-mcp-adapters · SQLAlchemy async · React + SWR

---

## 调用链路

```
Agent 调用 mcp_call(server, tool, arguments)
  │
  ▼ LangGraph 层
McpApprovalMiddleware.awrap_tool_call
  ├─ approval=confirm → interrupt() 触发 HITL，等用户确认
  └─ approval=auto/confirm后批准 → handler(request)
  │
  ▼ mcp_call @tool 执行
McpManager.call(server, tool, arguments)
  → tool.ainvoke(arguments)
  │
  ▼ MCP 层 (tool_interceptors)
deny_interceptor
  ├─ approval=deny → 返回 ToolMessage("Blocked")
  └─ 其他 → handler(request)
  │
  ▼ 实际 MCP Server
```

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `backend/choreo/mcp/__init__.py` | `get_mcp_manager()` / `set_mcp_manager()` 全局单例 |
| 新建 | `backend/choreo/mcp/manager.py` | `McpManager` — 无状态 client + 工具发现 + deny interceptor |
| 新建 | `backend/choreo/agents/tools/mcp_tool.py` | `mcp_call` LangChain @tool |
| 新建 | `backend/choreo/agents/middlewares/mcp_context.py` | `McpContextMiddleware` — 注入紧凑目录 |
| 新建 | `backend/choreo/agents/middlewares/mcp_approval.py` | `McpApprovalMiddleware` — 仅处理 confirm HITL |
| 新建 | `backend/tests/test_mcp_manager.py` | McpManager 单元测试 |
| 修改 | `backend/choreo/agents/middlewares/__init__.py` | 导出两个新 middleware |
| 修改 | `backend/choreo/agents/choreo_agent.py` | 加入 mcp_call + 两个 middleware |
| 修改 | `backend/choreo/gateway/app.py` | McpManager lifespan 集成 |
| 修改 | `backend/choreo/gateway/routers/mcp.py` | 加 `/reload` 和 `/tools` 端点 |
| 修改 | `frontend/src/components/ReviewPanel/ReviewPanel.tsx` | MCP 工具特殊渲染 |
| 修改 | `frontend/src/components/Chat/ChatMessage.tsx` | mcp_call ToolCallCard |
| 修改 | `frontend/src/pages/CustomizeMcpPage.tsx` | 「发现工具」按钮 |

---

## Task 1: 安装依赖（已完成）

依赖 `langchain-mcp-adapters` 已在上一阶段安装。

- [x] **Step 1: 验证可导入**

```bash
cd backend
uv run python -c "from langchain_mcp_adapters.client import MultiServerMCPClient; print('OK')"
```

期望输出: `OK`

---

## Task 2: McpManager 全局单例 + 骨架

**文件：**
- 新建: `backend/choreo/mcp/__init__.py`
- 新建: `backend/choreo/mcp/manager.py`

- [ ] **Step 1: 新建 `__init__.py`**

```python
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
```

- [ ] **Step 2: 新建 `manager.py` 骨架**

```python
# backend/choreo/mcp/manager.py
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class ToolInfo:
    name: str
    description: str
    server: str


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
                    return ToolMessage(
                        content=f"Tool '{server_name}/{tool_name}' is blocked by policy.",
                        tool_call_id=request.runtime.tool_call_id,
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
    except Exception:
        pass
    return "confirm"
```

- [ ] **Step 3: 写骨架测试**

```python
# backend/tests/test_mcp_manager.py
import pytest
from choreo.mcp.manager import McpManager


@pytest.mark.asyncio
async def test_manager_starts_empty():
    manager = McpManager()
    assert manager.get_all_tools_info() == {}
    assert manager._tool_registry == {}


@pytest.mark.asyncio
async def test_manager_reload_is_safe_when_no_servers():
    manager = McpManager()
    await manager.reload()   # _load_configs 返回空，不应报错
    assert manager._client is None


@pytest.mark.asyncio
async def test_call_returns_error_for_unknown_server():
    manager = McpManager()
    result = await manager.call("nonexistent", "some_tool", {})
    assert "not found" in result.lower() or "not connected" in result.lower()
```

- [ ] **Step 4: 运行测试（期望 3 个 PASS，call 测试因骨架返回 "" 可能需调整）**

```bash
cd backend
uv run pytest tests/test_mcp_manager.py -v
```

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/mcp/ backend/tests/test_mcp_manager.py
git commit -m "feat(mcp): add McpManager skeleton with deny interceptor pattern"
```

---

## Task 3: McpManager — 完整实现

**文件：**
- 修改: `backend/choreo/mcp/manager.py`

- [ ] **Step 1: 实现 `_load_configs`**

```python
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
```

- [ ] **Step 2: 实现 `_discover_all`**

```python
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
```

- [ ] **Step 3: 实现 `get_index` 和 `call`**

```python
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
            lines.append(f"  {t.name}: {desc}")

    return "\n".join(lines) if len(lines) > 1 else ""


async def call(self, server: str, tool: str, arguments: dict) -> str:
    """通过注册表找到工具并调用，结果经过 deny_interceptor。"""
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
```

- [ ] **Step 4: 补充测试**

```python
# 在 test_mcp_manager.py 追加
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
    from unittest.mock import MagicMock
    manager = McpManager()
    manager._tool_registry["myserver"] = {}  # empty tools
    result = await manager.call("myserver", "nonexistent", {})
    assert "not found" in result
```

- [ ] **Step 5: 运行测试**

```bash
uv run pytest tests/test_mcp_manager.py -v
```

期望: 6 个测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/mcp/manager.py backend/tests/test_mcp_manager.py
git commit -m "feat(mcp): implement McpManager discover/index/call with deny interceptor"
```

---

## Task 4: mcp_call 工具

**文件：**
- 新建: `backend/choreo/agents/tools/mcp_tool.py`

- [ ] **Step 1: 新建工具**

```python
# backend/choreo/agents/tools/mcp_tool.py
from langchain_core.tools import tool
from choreo.mcp import get_mcp_manager


@tool
async def mcp_call(server: str, tool: str, arguments: dict) -> str:
    """Call a tool on an MCP server.

    Use this when you see tools listed under "Available MCP Tools" in the
    system prompt. Pass the server name, tool name, and arguments exactly
    as shown.

    Args:
        server: MCP server name (e.g. "github", "postgres")
        tool: Tool name to call (e.g. "create_issue", "query")
        arguments: Arguments dict for the tool

    Returns:
        Tool execution result as string.
    """
    return await get_mcp_manager().call(server, tool, arguments)
```

- [ ] **Step 2: 验证可导入**

```bash
uv run python -c "from choreo.agents.tools.mcp_tool import mcp_call; print(mcp_call.name)"
```

期望输出: `mcp_call`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/agents/tools/mcp_tool.py
git commit -m "feat(mcp): add mcp_call proxy tool"
```

---

## Task 5: McpContextMiddleware

**文件：**
- 新建: `backend/choreo/agents/middlewares/mcp_context.py`

- [ ] **Step 1: 新建 middleware**

```python
# backend/choreo/agents/middlewares/mcp_context.py
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from choreo.mcp import get_mcp_manager


class McpContextMiddleware(AgentMiddleware):
    """在每次 LLM 调用前将紧凑 MCP 工具目录追加到 system prompt。

    只显示 approval != deny 且 enabled=true 的工具名和描述，
    不注入完整 JSON schema，避免 context 膨胀。
    """

    async def awrap_model_call(self, request, handler):
        try:
            index = await get_mcp_manager().get_index()
        except RuntimeError:
            return await handler(request)

        if index:
            existing = request.system_message.content if request.system_message else ""
            new_content = f"{existing}\n\n{index}" if existing else index
            request = request.override(
                system_message=SystemMessage(content=new_content)
            )
        return await handler(request)
```

- [ ] **Step 2: 验证**

```bash
uv run python -c "from choreo.agents.middlewares.mcp_context import McpContextMiddleware; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/agents/middlewares/mcp_context.py
git commit -m "feat(mcp): add McpContextMiddleware for tool index injection"
```

---

## Task 6: McpApprovalMiddleware（仅处理 confirm）

**文件：**
- 新建: `backend/choreo/agents/middlewares/mcp_approval.py`

- [ ] **Step 1: 新建 middleware**

```python
# backend/choreo/agents/middlewares/mcp_approval.py
from langchain.agents.middleware import AgentMiddleware
from langgraph.types import interrupt


class McpApprovalMiddleware(AgentMiddleware):
    """在 LangGraph 层拦截 mcp_call 工具调用，处理 confirm 审批。

    只处理 approval=confirm 的情况（触发 HITL interrupt）。
    approval=deny 由 MCP 层的 deny_interceptor 处理。
    approval=auto 两层都放行。
    """

    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] != "mcp_call":
            return await handler(request)

        args = request.tool_call.get("args", {})
        server = args.get("server", "")
        tool_name = args.get("tool", "")
        arguments = args.get("arguments", {})
        tool_call_id = request.tool_call.get("id", "")

        approval = await _get_approval(server, tool_name)

        if approval == "confirm":
            decision = interrupt({
                "action_requests": [{
                    "name": f"{server} · {tool_name}",
                    "arguments": arguments,
                }],
                "review_configs": [{
                    "action_name": f"{server} · {tool_name}",
                    "allowed_decisions": ["approve", "reject"],
                }],
            })
            decisions = (decision or {}).get("decisions", [])
            if decisions and decisions[0].get("type") == "reject":
                from langchain_core.messages import ToolMessage
                return ToolMessage(
                    content=f"Tool '{server}/{tool_name}' was rejected by user.",
                    tool_call_id=tool_call_id,
                )

        # approval=auto 或 confirm 批准后：放行执行
        return await handler(request)


async def _get_approval(server: str, tool: str) -> str:
    """从 DB 读取工具的 approval 配置，默认 confirm。"""
    from choreo.db import SessionLocal, McpServerRow
    try:
        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server)
            if row and row.tools_config:
                return row.tools_config.get(tool, {}).get("approval", "confirm")
    except Exception:
        pass
    return "confirm"
```

- [ ] **Step 2: 验证**

```bash
uv run python -c "from choreo.agents.middlewares.mcp_approval import McpApprovalMiddleware; print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/agents/middlewares/mcp_approval.py
git commit -m "feat(mcp): add McpApprovalMiddleware for confirm-only HITL"
```

---

## Task 7: 导出 + 注册到 Agent

**文件：**
- 修改: `backend/choreo/agents/middlewares/__init__.py`
- 修改: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: 更新 `__init__.py`**

```python
# backend/choreo/agents/middlewares/__init__.py
from choreo.agents.middlewares.call_limit import ModelCallLimitMiddleware
from choreo.agents.middlewares.human_in_loop import store_decision, pop_decision
from choreo.agents.middlewares.title import TitleMiddleware
from choreo.agents.middlewares.model_selector import ModelSelectorMiddleware
from choreo.agents.middlewares.skills_context import SkillsContextMiddleware
from choreo.agents.middlewares.mcp_context import McpContextMiddleware
from choreo.agents.middlewares.mcp_approval import McpApprovalMiddleware

__all__ = [
    "ModelCallLimitMiddleware",
    "store_decision", "pop_decision",
    "TitleMiddleware",
    "ModelSelectorMiddleware",
    "SkillsContextMiddleware",
    "McpContextMiddleware",
    "McpApprovalMiddleware",
]
```

- [ ] **Step 2: 更新 `choreo_agent.py`**

```python
# backend/choreo/agents/choreo_agent.py
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from choreo.model_factory import load_model
from choreo.agents.tools import (
    read_git_log, send_notification, read_file, write_file,
    edit_file, list_dir, grep, bash, skill_view,
)
from choreo.agents.tools.mcp_tool import mcp_call
from choreo.agents.middlewares import (
    ModelCallLimitMiddleware, TitleMiddleware,
    ModelSelectorMiddleware, SkillsContextMiddleware,
    McpContextMiddleware, McpApprovalMiddleware,
)
from choreo.config import settings

llm = load_model()


def create_choreo_agent(checkpointer):
    return create_agent(
        model=llm,
        tools=[
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_view,
            mcp_call,
        ],
        system_prompt=(
            "你是 Choreo，一个开发自动化 Agent。帮助用户把重复的开发杂活变成自动运行的脚本。\n"
            "你有以下工具：\n"
            "- read_git_log：读取 git commit 历史\n"
            "- read_file / write_file / edit_file：读写和精确编辑文件\n"
            "- list_dir / grep：目录浏览和内容搜索\n"
            "- bash：执行 bash 命令（需用户确认）\n"
            "- send_notification：发送通知（需用户确认）\n"
            "- skill_view：读取技能库中某个技能（从 Available Skills 列表找 ID）\n"
            "- mcp_call：调用 MCP server 工具（从 Available MCP Tools 列表找 server/tool）\n"
            "\n"
            "修改文件前先用 read_file；执行 bash 和发送通知前必须等用户确认。"
        ),
        middleware=[
            McpContextMiddleware(),     # 最外层：注入 MCP 工具目录
            SkillsContextMiddleware(),  # 注入 Skills 目录
            McpApprovalMiddleware(),    # confirm 类型 MCP 工具的 HITL
            ModelSelectorMiddleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "bash": {
                        "description": "即将执行 bash 命令，请确认",
                        "allowed_decisions": ["approve", "edit", "reject"],
                    },
                    "send_notification": {
                        "description": "即将发送通知，请确认",
                        "allowed_decisions": ["approve", "reject"],
                    },
                }
            ),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
            TitleMiddleware(llm=llm, max_chars=20),
        ],
        checkpointer=checkpointer,
    )
```

- [ ] **Step 3: 验证**

```bash
uv run python -c "from choreo.agents.choreo_agent import create_choreo_agent; print('OK')"
```

期望输出: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/choreo/agents/middlewares/__init__.py backend/choreo/agents/choreo_agent.py
git commit -m "feat(mcp): register mcp_call + MCP middlewares in choreo agent"
```

---

## Task 8: lifespan 集成

**文件：**
- 修改: `backend/choreo/gateway/app.py`

- [ ] **Step 1: 更新 `app.py`**

在 import 末尾加：
```python
from choreo.mcp import McpManager, set_mcp_manager
```

在 `lifespan` 的 `set_skill_store` 之后、`init_db()` 之前加：
```python
    # 初始化 McpManager（连接失败不阻塞启动）
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()
```

在 yield 之后的清理注释后加（McpManager 无状态，无需显式关闭，但保留 reload 能力）：
```python
    # mcp_manager 无状态，client 自动管理，无需显式 shutdown
```

- [ ] **Step 2: 验证启动**

```bash
uv run uvicorn choreo.gateway.app:app --reload &
sleep 4
curl -s http://localhost:8000/api/mcp/ | python -m json.tool
kill %1
```

期望: 返回 JSON 数组，无 500。

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/gateway/app.py
git commit -m "feat(mcp): integrate McpManager into FastAPI lifespan"
```

---

## Task 9: /reload 和 /tools 端点

**文件：**
- 修改: `backend/choreo/gateway/routers/mcp.py`

- [ ] **Step 1: 追加两个端点到 `mcp.py` 末尾**

```python
@router.post("/reload")
async def reload_mcp():
    """重新加载所有 MCP server 配置和工具，不重启进程。"""
    from choreo.mcp import get_mcp_manager
    try:
        manager = get_mcp_manager()
        await manager.reload()
        return {
            "status": "ok",
            "servers": list(manager.get_all_tools_info().keys()),
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/tools")
async def get_mcp_tools():
    """返回内存中已发现的工具列表（实时状态）。"""
    from choreo.mcp import get_mcp_manager
    try:
        return get_mcp_manager().get_all_tools_info()
    except RuntimeError:
        return {}
```

- [ ] **Step 2: 验证端点**

```bash
uv run uvicorn choreo.gateway.app:app &
sleep 4
curl -s -X POST http://localhost:8000/api/mcp/reload | python -m json.tool
curl -s http://localhost:8000/api/mcp/tools | python -m json.tool
kill %1
```

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/gateway/routers/mcp.py
git commit -m "feat(mcp): add /reload and /tools endpoints"
```

---

## Task 10: 前端 — ReviewPanel MCP 渲染

**文件：**
- 修改: `frontend/src/components/ReviewPanel/ReviewPanel.tsx`

- [ ] **Step 1: 加 server 图标映射并更新渲染**

在文件顶部 `TOOL_ICONS` 后加：
```tsx
const MCP_SERVER_ICONS: Record<string, string> = {
  github: "🐙", postgres: "🐘", filesystem: "🗂️",
  slack: "💬", notion: "📝", "brave-search": "🔍",
};
```

在 `ReviewPanel` 函数内，`icon` 和 `args` 的计算替换为：
```tsx
  const isMcpTool = action?.name?.includes(" · ");
  const [mcpServer, mcpTool] = isMcpTool
    ? action.name.split(" · ", 2)
    : ["", ""];

  // MCP 工具展示内层 arguments；普通工具展示外层 args
  const displayArgs = isMcpTool ? (args.arguments ?? args) : args;
  const icon = isMcpTool
    ? (MCP_SERVER_ICONS[mcpServer] ?? "🔌")
    : (TOOL_ICONS[action?.name] ?? "◆");
```

将工具名行替换为：
```tsx
          <div className="flex items-center gap-2.5 px-4 pt-3 pb-2 border-b border-[#1a1a1a]">
            <span className="text-[#e2b714] text-[14px]">{icon}</span>
            {isMcpTool ? (
              <>
                <span className="text-[#e2b714] text-[13px] font-semibold">{mcpServer}</span>
                <span className="text-[#555] text-[13px] mx-1">·</span>
                <span className="text-[#e2b714] text-[13px] font-semibold">{mcpTool}</span>
              </>
            ) : (
              <span className="text-[#e2b714] text-[13px] font-semibold">{action?.name}</span>
            )}
          </div>
```

将参数列表的 `args` 改为 `displayArgs`：
```tsx
          {Object.keys(displayArgs).length > 0 && (
            <div className="px-4 py-3 space-y-2.5 border-b border-[#1a1a1a]">
              {Object.entries(displayArgs).map(([key, val]) => {
```

- [ ] **Step 2: TypeScript 检查**

```bash
cd frontend && npx tsc --noEmit 2>&1
```

期望: 无报错。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ReviewPanel/ReviewPanel.tsx
git commit -m "feat(mcp): update ReviewPanel for MCP tool confirmation display"
```

---

## Task 11: 前端 — ChatMessage mcp_call 卡片

**文件：**
- 修改: `frontend/src/components/Chat/ChatMessage.tsx`

- [ ] **Step 1: 加 server 图标映射 + 更新 ToolCallCard**

在文件顶部（`TOOL_TYPES` 后）加：
```tsx
const MCP_SERVER_ICONS: Record<string, string> = {
  github: "🐙", postgres: "🐘", filesystem: "🗂️",
  slack: "💬", notion: "📝", "brave-search": "🔍",
};
```

在 `ToolCallCard` 函数开头加 mcp 解析逻辑：
```tsx
  const isMcp = toolCall.name === "mcp_call";
  const mcpServer = isMcp ? String(toolCall.args.server ?? "") : "";
  const mcpTool   = isMcp ? String(toolCall.args.tool ?? "") : "";
  const displayArgs = isMcp
    ? (toolCall.args.arguments ?? {}) as Record<string, unknown>
    : toolCall.args;
  const displayName = isMcp ? `${mcpServer} · ${mcpTool}` : toolCall.name;
  const type = isMcp
    ? {
        label: mcpServer || "MCP",
        bar: "bg-violet-500",
        badge: "bg-violet-100 dark:bg-violet-950",
        badgeText: "text-violet-700 dark:text-violet-300",
        cardBg: "bg-[#faf8ff] dark:bg-[#110f1f]",
        cardBorder: "border-violet-100 dark:border-violet-900/50",
      }
    : getToolType(toolCall.name);
```

将 header 中的工具名部分替换为：
```tsx
          <span className={`text-[9.5px] font-bold px-1.5 py-0.5 rounded-md flex-shrink-0 ${type.badge} ${type.badgeText} uppercase tracking-wide`}>
            {isMcp ? "MCP" : type.label}
          </span>
          {isMcp && (
            <span className="text-[11px] flex-shrink-0">
              {MCP_SERVER_ICONS[mcpServer] ?? "🔌"}
            </span>
          )}
          <span className="font-mono text-[11.5px] font-semibold text-[#1e293b] dark:text-[#d0d0d0] flex-shrink-0">
            {displayName}
          </span>
```

将展开体的参数从 `toolCall.args` 改为 `displayArgs`：
```tsx
          <pre ...>{JSON.stringify(displayArgs, null, 2)}</pre>
```

- [ ] **Step 2: TypeScript 检查**

```bash
npx tsc --noEmit 2>&1
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Chat/ChatMessage.tsx
git commit -m "feat(mcp): render mcp_call cards with server icon and inner args"
```

---

## Task 12: 前端 — MCP 页面「发现工具」按钮

**文件：**
- 修改: `frontend/src/api/mcp.ts`
- 修改: `frontend/src/pages/CustomizeMcpPage.tsx`

- [ ] **Step 1: 在 `api/mcp.ts` 追加两个函数**

```typescript
export const reloadServers = (): Promise<{ status: string; servers: string[] }> =>
  fetch(`${BASE}/reload`, { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

export const getDiscoveredTools = (): Promise<
  Record<string, Array<{ name: string; description: string }>>
> => fetch(`${BASE}/tools`).then((r) => r.json());
```

- [ ] **Step 2: 在 `CustomizeMcpPage.tsx` 添加发现工具逻辑**

import 行加 `reloadServers`：
```tsx
import { listServers, createServer, patchServer, deleteServer, reloadServers } from "@/api/mcp";
```

state 区加：
```tsx
const [discovering, setDiscovering] = useState(false);
```

加 `discoverTools` 函数：
```tsx
const discoverTools = async () => {
  if (!selectedSkill) return;  // 需选中一个 server
  setDiscovering(true);
  try {
    await reloadServers();
    await refresh();
  } catch (e) {
    console.error("Discover failed:", e);
  } finally {
    setDiscovering(false);
  }
};
```

在工具列表 Tab 顶部 header，「添加工具」按钮旁加：
```tsx
<button
  onClick={discoverTools}
  disabled={discovering}
  className="flex items-center gap-1.5 text-[11.5px] text-[#1e90ff] hover:text-[#1070cc] transition-colors disabled:opacity-40"
>
  <svg className={`w-3 h-3 ${discovering ? "animate-spin" : ""}`}
    viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M13.5 8A5.5 5.5 0 112.5 8" strokeLinecap="round"/>
    <path d="M13.5 4v4h-4"/>
  </svg>
  {discovering ? "发现中…" : "发现工具"}
</button>
```

- [ ] **Step 3: TypeScript 检查**

```bash
npx tsc --noEmit 2>&1
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/mcp.ts frontend/src/pages/CustomizeMcpPage.tsx
git commit -m "feat(mcp): add discover tools button with reload integration"
```

---

## 自检清单

- [x] `MultiServerMCPClient` 无状态模式，无需 `__aenter__/__aexit__`
- [x] `deny` 在 MCP 层（`deny_interceptor`）处理，`McpApprovalMiddleware` 只处理 `confirm`
- [x] `_tool_to_server` 映射供 interceptor 查 server 名，已知局限：同名工具跨 server 会冲突
- [x] `_discover_all` 并发执行，单个 server 失败不影响其他
- [x] `_sync_to_db` 保留已有用户 approval 配置
- [x] `get_index()` 过滤 deny/disabled 工具，不注入 JSON schema
- [x] ReviewPanel 识别 `server · tool` 格式并展示内层参数
- [x] ToolCallCard 对 `mcp_call` 显示 server 图标和 `{server} · {tool}` 名称
- [x] `/api/mcp/reload` 重建 client + 重新发现工具 + 同步 DB
