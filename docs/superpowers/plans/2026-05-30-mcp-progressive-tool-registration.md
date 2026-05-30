# MCP 工具渐进式注册机制 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 实现 MCP 工具的渐进式注册——Agent 工具列表只注册一个 `mcp_call` 代理工具，通过 `McpContextMiddleware` 动态注入紧凑工具目录文字，通过 `McpApprovalMiddleware` 按 DB 配置做审批拦截。

**架构：** McpManager 在 lifespan 启动时连接所有 enabled MCP server、发现工具并同步到 DB。`mcp_call` 工具代理调用实际 MCP server。两个中间件分别处理 context 注入和审批逻辑。

**技术栈：** FastAPI lifespan · LangGraph AgentMiddleware · langchain-mcp-adapters · SQLAlchemy async · React + SWR

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `backend/choreo/mcp/__init__.py` | `get_mcp_manager()` / `set_mcp_manager()` 全局单例 |
| 新建 | `backend/choreo/mcp/manager.py` | `McpManager` — 连接池 + 工具发现 + 调用代理 |
| 新建 | `backend/choreo/agents/tools/mcp_tool.py` | `mcp_call` LangChain @tool |
| 新建 | `backend/choreo/agents/middlewares/mcp_context.py` | `McpContextMiddleware` — 注入紧凑目录 |
| 新建 | `backend/choreo/agents/middlewares/mcp_approval.py` | `McpApprovalMiddleware` — 审批拦截 |
| 新建 | `backend/tests/test_mcp_manager.py` | McpManager 单元测试 |
| 修改 | `backend/choreo/agents/middlewares/__init__.py` | 导出两个新 middleware |
| 修改 | `backend/choreo/agents/choreo_agent.py` | 加入 mcp_call + 两个 middleware |
| 修改 | `backend/choreo/gateway/app.py` | McpManager lifespan 集成 |
| 修改 | `backend/choreo/gateway/routers/mcp.py` | 加 `/reload` 和 `/tools` 端点 |
| 修改 | `frontend/src/components/ReviewPanel/ReviewPanel.tsx` | MCP 工具特殊渲染 |
| 修改 | `frontend/src/components/Chat/ChatMessage.tsx` | mcp_call ToolCallCard 显示 |
| 修改 | `frontend/src/pages/CustomizeMcpPage.tsx` | 加「发现工具」按钮 |

---

## Task 1: 安装依赖

**文件：**
- 修改: `backend/pyproject.toml`

- [ ] **Step 1: 安装 langchain-mcp-adapters**

```bash
cd backend
uv add langchain-mcp-adapters
```

期望输出: `Added langchain-mcp-adapters` 及版本号，无报错。

- [ ] **Step 2: 验证可导入**

```bash
uv run python -c "from langchain_mcp_adapters.client import MultiServerMCPClient; print('OK')"
```

期望输出: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: add langchain-mcp-adapters dependency"
```

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
from typing import Any

logger = logging.getLogger(__name__)


class ToolInfo:
    def __init__(self, name: str, description: str, server: str) -> None:
        self.name = name
        self.description = description
        self.server = server


class McpManager:
    """管理 MCP server 连接生命周期，提供工具发现和调用能力。"""

    def __init__(self) -> None:
        # {server_name: {"client": MCPClient, "tools": list[ToolInfo]}}
        self._registry: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        """在 lifespan 启动时调用：连接所有 enabled server，发现工具，同步 DB。"""
        await self._connect_all()

    async def reload(self) -> None:
        """重新连接所有 server，不重启进程。供 /api/mcp/reload 调用。"""
        await self.shutdown()
        self._registry = {}
        await self._connect_all()

    async def shutdown(self) -> None:
        """关闭所有 MCP 连接。"""
        for name, entry in self._registry.items():
            client = entry.get("client")
            if client is not None:
                try:
                    await client.__aexit__(None, None, None)
                except Exception:
                    pass
        self._registry = {}

    async def _connect_all(self) -> None:
        """从 DB 读取 enabled servers，并发连接，超时 10s 跳过。"""
        pass  # Task 3 实现

    async def get_index(self) -> str:
        """生成紧凑工具目录文字，过滤掉 approval=deny 的工具。"""
        return ""  # Task 4 实现

    async def call(self, server: str, tool: str, arguments: dict) -> str:
        """通过 MCP 协议调用指定 server 的工具。"""
        return ""  # Task 4 实现

    def get_all_tools_info(self) -> dict[str, list[dict]]:
        """返回所有已发现工具的信息，供 /api/mcp/tools 端点使用。"""
        result: dict[str, list[dict]] = {}
        for server, entry in self._registry.items():
            result[server] = [
                {"name": t.name, "description": t.description}
                for t in entry.get("tools", [])
            ]
        return result
```

- [ ] **Step 3: 写骨架测试**

```python
# backend/tests/test_mcp_manager.py
import pytest
from unittest.mock import AsyncMock, patch
from choreo.mcp.manager import McpManager


@pytest.mark.asyncio
async def test_manager_starts_empty():
    manager = McpManager()
    assert manager.get_all_tools_info() == {}


@pytest.mark.asyncio
async def test_manager_shutdown_is_safe_when_empty():
    manager = McpManager()
    await manager.shutdown()  # 不应抛出异常
```

- [ ] **Step 4: 运行测试**

```bash
cd backend
uv run pytest tests/test_mcp_manager.py -v
```

期望: 2 个测试 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/mcp/ backend/tests/test_mcp_manager.py
git commit -m "feat(mcp): add McpManager skeleton and global accessor"
```

---

## Task 3: McpManager — 连接与工具发现

**文件：**
- 修改: `backend/choreo/mcp/manager.py`

- [ ] **Step 1: 实现 `_connect_all`**

替换 `manager.py` 中的 `_connect_all` 方法：

```python
async def _connect_all(self) -> None:
    from choreo.db import SessionLocal, McpServerRow
    from sqlalchemy import select

    async with SessionLocal() as session:
        result = await session.execute(
            select(McpServerRow).where(McpServerRow.enabled == True)
        )
        servers = list(result.scalars())

    if not servers:
        logger.info("No enabled MCP servers found.")
        return

    tasks = [self._connect_one(s) for s in servers]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _connect_one(self, server_row) -> None:
    from langchain_mcp_adapters.client import MultiServerMCPClient

    name = server_row.name
    try:
        if server_row.transport == "stdio":
            if not server_row.command:
                logger.warning("MCP server '%s' has no command, skipping.", name)
                return
            cfg = {
                name: {
                    "command": server_row.command,
                    "args": server_row.args or [],
                    "env": server_row.env or {},
                    "transport": "stdio",
                }
            }
        else:
            if not server_row.url:
                logger.warning("MCP server '%s' has no url, skipping.", name)
                return
            cfg = {
                name: {
                    "url": server_row.url,
                    "transport": server_row.transport,
                }
            }

        client = MultiServerMCPClient(cfg)
        await asyncio.wait_for(client.__aenter__(), timeout=10.0)

        raw_tools = await client.get_tools()
        tools: list[ToolInfo] = []
        # langchain-mcp-adapters 返回的工具名格式: "{server}__{tool}" 或直接 "{tool}"
        for t in raw_tools:
            tool_name = t.name
            if "__" in tool_name:
                _, tool_name = tool_name.split("__", 1)
            tools.append(ToolInfo(
                name=tool_name,
                description=(t.description or "").split("\n")[0][:120],
                server=name,
            ))

        self._registry[name] = {"client": client, "tools": tools, "lc_tools": raw_tools}
        logger.info("Connected MCP server '%s' with %d tools.", name, len(tools))

        # 同步工具到 DB
        await self._sync_tools_to_db(name, tools, server_row.tools_config or {})

    except asyncio.TimeoutError:
        logger.warning("MCP server '%s' connection timed out (10s), skipping.", name)
    except Exception as e:
        logger.warning("MCP server '%s' connection failed: %s", name, e)
```

- [ ] **Step 2: 实现 `_sync_tools_to_db`**

```python
async def _sync_tools_to_db(
    self, server_name: str, tools: list[ToolInfo], existing_config: dict
) -> None:
    """将发现的工具同步到 DB tools_config，保留已有的用户配置。"""
    from choreo.db import SessionLocal, McpServerRow

    new_config: dict = {}
    for tool in tools:
        if tool.name in existing_config:
            new_config[tool.name] = existing_config[tool.name]
        else:
            new_config[tool.name] = {"approval": "confirm", "enabled": True}

    async with SessionLocal() as session:
        row = await session.get(McpServerRow, server_name)
        if row:
            row.tools_config = new_config
            await session.commit()
```

- [ ] **Step 3: 实现 `get_index` 和 `call`**

```python
async def get_index(self) -> str:
    """生成紧凑工具目录，过滤 approval=deny 的工具。"""
    from choreo.db import SessionLocal, McpServerRow
    from sqlalchemy import select

    # 读取所有 server 的 tools_config
    async with SessionLocal() as session:
        result = await session.execute(select(McpServerRow))
        configs: dict[str, dict] = {
            r.name: r.tools_config or {} for r in result.scalars()
        }

    if not self._registry:
        return ""

    lines = ["Available MCP Tools (use mcp_call to invoke):"]
    for server_name, entry in self._registry.items():
        server_cfg = configs.get(server_name, {})
        visible_tools = [
            t for t in entry.get("tools", [])
            if server_cfg.get(t.name, {}).get("approval", "confirm") != "deny"
            and server_cfg.get(t.name, {}).get("enabled", True)
        ]
        if not visible_tools:
            continue
        lines.append(f"\n{server_name}:")
        for t in visible_tools:
            lines.append(f"  {t.name}: {t.description}")

    return "\n".join(lines) if len(lines) > 1 else ""


async def call(self, server: str, tool: str, arguments: dict) -> str:
    """通过已建立的 MCP 连接调用工具。"""
    entry = self._registry.get(server)
    if entry is None:
        return f"MCP server '{server}' is not connected."

    # 找到对应的 LangChain tool 对象
    lc_tools: list = entry.get("lc_tools", [])
    target = None
    for t in lc_tools:
        # 工具名可能是 "{server}__{tool}" 或 "{tool}"
        short_name = t.name.split("__", 1)[-1] if "__" in t.name else t.name
        if short_name == tool:
            target = t
            break

    if target is None:
        return f"Tool '{tool}' not found in MCP server '{server}'."

    try:
        result = await target.ainvoke(arguments)
        return str(result)
    except Exception as e:
        return f"MCP tool call failed: {e}"
```

- [ ] **Step 4: 补充测试**

```python
# 在 test_mcp_manager.py 追加
@pytest.mark.asyncio
async def test_get_index_returns_empty_when_no_servers():
    manager = McpManager()
    index = await manager.get_index()
    assert index == ""


@pytest.mark.asyncio
async def test_call_returns_error_for_unknown_server():
    manager = McpManager()
    result = await manager.call("nonexistent", "some_tool", {})
    assert "not connected" in result
```

- [ ] **Step 5: 运行测试**

```bash
uv run pytest tests/test_mcp_manager.py -v
```

期望: 4 个测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/mcp/manager.py backend/tests/test_mcp_manager.py
git commit -m "feat(mcp): implement McpManager connect, discover, and call"
```

---

## Task 4: mcp_call 工具

**文件：**
- 新建: `backend/choreo/agents/tools/mcp_tool.py`

- [ ] **Step 1: 新建工具文件**

```python
# backend/choreo/agents/tools/mcp_tool.py
from langchain_core.tools import tool
from choreo.mcp import get_mcp_manager


@tool
async def mcp_call(server: str, tool: str, arguments: dict) -> str:
    """Call a tool on an MCP server.

    Use this when you see a tool listed under "Available MCP Tools" in
    the system prompt. Pass the server name, tool name, and arguments exactly.

    Args:
        server: MCP server name as shown in the tools index (e.g. "github")
        tool: Tool name to call (e.g. "create_issue")
        arguments: Arguments dict for the tool (keys/values depend on the tool)

    Returns:
        Tool execution result as a string.
    """
    return await get_mcp_manager().call(server, tool, arguments)
```

- [ ] **Step 2: 验证工具可导入**

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

    只追加 approval != deny 且 enabled=true 的工具，不注入完整 JSON schema。
    """

    async def awrap_model_call(self, request, handler):
        try:
            index = await get_mcp_manager().get_index()
        except RuntimeError:
            # McpManager 未初始化时（测试环境）不影响正常运行
            return await handler(request)

        if index:
            existing = request.system_message.content if request.system_message else ""
            new_content = f"{existing}\n\n{index}" if existing else index
            request = request.override(
                system_message=SystemMessage(content=new_content)
            )
        return await handler(request)
```

- [ ] **Step 2: 验证可导入**

```bash
uv run python -c "from choreo.agents.middlewares.mcp_context import McpContextMiddleware; print('OK')"
```

期望输出: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/agents/middlewares/mcp_context.py
git commit -m "feat(mcp): add McpContextMiddleware for tool index injection"
```

---

## Task 6: McpApprovalMiddleware

**文件：**
- 新建: `backend/choreo/agents/middlewares/mcp_approval.py`

- [ ] **Step 1: 新建 middleware**

```python
# backend/choreo/agents/middlewares/mcp_approval.py
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import interrupt


class McpApprovalMiddleware(AgentMiddleware):
    """拦截 mcp_call 工具调用，根据 DB tools_config 的 approval 字段决定处理方式。

    - approval=auto    → 直接放行
    - approval=confirm → HITL interrupt，等用户确认
    - approval=deny    → 返回 blocked 消息，不执行
    """

    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] != "mcp_call":
            return await handler(request)

        args = request.tool_call.get("args", {})
        server = args.get("server", "")
        tool_name = args.get("tool", "")
        arguments = args.get("arguments", {})
        tool_call_id = request.tool_call.get("id", "")

        approval = await self._get_approval(server, tool_name)

        if approval == "deny":
            return ToolMessage(
                content=f"Tool '{server}/{tool_name}' is blocked by policy.",
                tool_call_id=tool_call_id,
            )

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
            # decision = {"decisions": [{"type": "approve"}]} 或 {"decisions": [{"type": "reject"}]}
            decisions = decision.get("decisions", []) if isinstance(decision, dict) else []
            if decisions and decisions[0].get("type") == "reject":
                return ToolMessage(
                    content=f"Tool '{server}/{tool_name}' was rejected by user.",
                    tool_call_id=tool_call_id,
                )

        # approval=auto 或 confirm 后批准：执行
        return await handler(request)

    @staticmethod
    async def _get_approval(server: str, tool_name: str) -> str:
        """从 DB 读取工具的 approval 配置，默认 confirm。"""
        from choreo.db import SessionLocal, McpServerRow

        try:
            async with SessionLocal() as session:
                row = await session.get(McpServerRow, server)
                if row and row.tools_config:
                    cfg = row.tools_config.get(tool_name, {})
                    return cfg.get("approval", "confirm")
        except Exception:
            pass
        return "confirm"
```

- [ ] **Step 2: 验证可导入**

```bash
uv run python -c "from choreo.agents.middlewares.mcp_approval import McpApprovalMiddleware; print('OK')"
```

期望输出: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/agents/middlewares/mcp_approval.py
git commit -m "feat(mcp): add McpApprovalMiddleware for per-tool HITL control"
```

---

## Task 7: 导出 + 注册到 Agent

**文件：**
- 修改: `backend/choreo/agents/middlewares/__init__.py`
- 修改: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: 更新 `middlewares/__init__.py`**

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
    "store_decision",
    "pop_decision",
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
    ModelCallLimitMiddleware,
    TitleMiddleware,
    ModelSelectorMiddleware,
    SkillsContextMiddleware,
    McpContextMiddleware,
    McpApprovalMiddleware,
)
from choreo.config import settings

llm = load_model()


def create_choreo_agent(checkpointer):
    """用给定的 checkpointer 创建 Choreo agent（在 lifespan 中调用）。"""
    return create_agent(
        model=llm,
        tools=[
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_view,
            mcp_call,  # MCP proxy 工具
        ],
        system_prompt=(
            "你是 Choreo，一个开发自动化 Agent。帮助用户把重复的开发杂活变成自动运行的脚本。\n"
            "你有以下工具：\n"
            "- read_git_log：读取 git commit 历史\n"
            "- read_file / write_file / edit_file：读写和精确编辑文件\n"
            "- list_dir / grep：目录浏览和内容搜索\n"
            "- bash：执行 bash 命令（需用户确认）\n"
            "- send_notification：发送通知（需用户确认）\n"
            "- skill_view：读取技能库中某个技能的完整内容（从系统消息的 Available Skills 列表中找到 ID 后调用）\n"
            "- mcp_call：调用 MCP server 工具（从系统消息的 Available MCP Tools 列表中找到 server/tool 后调用）\n"
            "\n"
            "修改文件前先用 read_file 了解内容；执行 bash 命令和发送通知前必须等用户确认。"
        ),
        middleware=[
            McpContextMiddleware(),    # 注入 MCP 工具目录（最外层）
            SkillsContextMiddleware(), # 注入 Skills 目录
            McpApprovalMiddleware(),   # MCP 工具审批拦截
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

- [ ] **Step 3: 验证语法无误**

```bash
uv run python -c "from choreo.agents.choreo_agent import create_choreo_agent; print('OK')"
```

期望输出: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/choreo/agents/middlewares/__init__.py backend/choreo/agents/choreo_agent.py
git commit -m "feat(mcp): register mcp_call tool and MCP middlewares in agent"
```

---

## Task 8: McpManager 集成到 lifespan

**文件：**
- 修改: `backend/choreo/gateway/app.py`

- [ ] **Step 1: 更新 lifespan**

在 `app.py` 的 import 末尾加：

```python
from choreo.mcp import McpManager, set_mcp_manager
```

在 `lifespan` 函数中，`set_skill_store` 之后、`init_db()` 之前加：

```python
    # 初始化 McpManager（连接 MCP servers，发现工具）
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()
```

在 `yield` 之后的清理部分加：

```python
    await mcp_manager.shutdown()
```

完整 lifespan 如下（仅展示变动部分，其余不变）：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. 初始化 SkillStore 并同步内置技能
    _cfg_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(_cfg_path, encoding="utf-8") as _f:
        _cfg = _yaml.safe_load(_f) or {}
    _skills_root = Path(__file__).parent.parent.parent / _cfg.get("skills_dir", "./skills")
    _skill_store = LocalSkillStore(_skills_root)
    await sync_builtin_skills(_skill_store)
    set_skill_store(_skill_store)

    # 0.5 初始化 McpManager
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()   # 连接失败不阻塞启动

    # 1. 建表（幂等）
    await init_db()

    # ... 其余代码不变 ...

    async with AsyncPostgresSaver.from_conn_string(settings.DATABASE_URL_PSYCOPG) as checkpointer:
        await checkpointer.setup()
        set_agent(create_choreo_agent(checkpointer))
        yield

    # 清理
    eviction_task.cancel()
    try:
        await eviction_task
    except asyncio.CancelledError:
        pass
    await manager.shutdown_all()
    await mcp_manager.shutdown()   # 新增
```

- [ ] **Step 2: 验证应用启动无报错**

```bash
uv run uvicorn choreo.gateway.app:app --reload &
sleep 3
curl http://localhost:8000/api/mcp/ | python -m json.tool
kill %1
```

期望: 返回 JSON 数组（即使为空 `[]`），无 500 错误。

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/gateway/app.py
git commit -m "feat(mcp): integrate McpManager into FastAPI lifespan"
```

---

## Task 9: /reload 和 /tools 端点

**文件：**
- 修改: `backend/choreo/gateway/routers/mcp.py`

- [ ] **Step 1: 在 `mcp.py` 路由末尾追加两个端点**

```python
# 在 routers/mcp.py 末尾追加

@router.post("/reload", status_code=200)
async def reload_mcp():
    """重新连接所有 enabled MCP server，刷新工具列表。不重启进程。"""
    from choreo.mcp import get_mcp_manager
    try:
        manager = get_mcp_manager()
        await manager.reload()
        return {"status": "ok", "servers": list(manager.get_all_tools_info().keys())}
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.get("/tools")
async def get_mcp_tools():
    """返回内存中已发现的工具列表（实时状态）。"""
    from choreo.mcp import get_mcp_manager
    try:
        manager = get_mcp_manager()
        return manager.get_all_tools_info()
    except RuntimeError:
        return {}
```

- [ ] **Step 2: 验证端点**

```bash
uv run uvicorn choreo.gateway.app:app &
sleep 3
curl -X POST http://localhost:8000/api/mcp/reload | python -m json.tool
curl http://localhost:8000/api/mcp/tools | python -m json.tool
kill %1
```

期望: 两个请求均返回 JSON，无 500 错误。

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/gateway/routers/mcp.py
git commit -m "feat(mcp): add /reload and /tools API endpoints"
```

---

## Task 10: 前端 — ReviewPanel MCP 渲染

**文件：**
- 修改: `frontend/src/components/ReviewPanel/ReviewPanel.tsx`

- [ ] **Step 1: 在 `TOOL_ICONS` 后加 server 图标映射，并更新渲染逻辑**

在文件顶部 `TOOL_ICONS` 下方添加：

```tsx
// MCP server 图标（server name → emoji）
const MCP_SERVER_ICONS: Record<string, string> = {
  github:     "🐙",
  postgres:   "🐘",
  filesystem: "🗂️",
  slack:      "💬",
  notion:     "📝",
  "brave-search": "🔍",
};
```

替换 `export default function ReviewPanel()` 中的 `icon` 和工具名行渲染部分：

```tsx
  // 检测是否是 MCP 工具（格式: "server · tool"）
  const isMcpTool = action?.name?.includes(" · ");
  const [mcpServer, mcpTool] = isMcpTool
    ? action.name.split(" · ", 2)
    : ["", ""];

  // 对 MCP 工具：展示内层 arguments；对普通工具：展示外层 args
  const displayArgs = isMcpTool
    ? (args.arguments ?? args)
    : args;

  const icon = isMcpTool
    ? (MCP_SERVER_ICONS[mcpServer] ?? "🔌")
    : (TOOL_ICONS[action?.name] ?? "◆");
```

将工具名行替换为：

```tsx
          {/* 工具名行 */}
          <div className="flex items-center gap-2.5 px-4 pt-3 pb-2 border-b border-[#1a1a1a]">
            <span className="text-[#e2b714] text-[14px]">{icon}</span>
            {isMcpTool ? (
              <>
                <span className="text-[#e2b714] text-[13px] font-semibold">{mcpServer}</span>
                <span className="text-[#555] text-[13px]">·</span>
                <span className="text-[#e2b714] text-[13px] font-semibold">{mcpTool}</span>
              </>
            ) : (
              <span className="text-[#e2b714] text-[13px] font-semibold">{action?.name}</span>
            )}
            {action?.description && (
              <span className="text-[#444] text-[11px] ml-1">{action.description}</span>
            )}
          </div>
```

将参数列表中的 `args` 替换为 `displayArgs`：

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
git commit -m "feat(mcp): update ReviewPanel to render MCP tool confirmations"
```

---

## Task 11: 前端 — ChatMessage mcp_call 展示

**文件：**
- 修改: `frontend/src/components/Chat/ChatMessage.tsx`

- [ ] **Step 1: 在 `TOOL_TYPES` 对象后加 MCP server 图标映射**

```tsx
const MCP_SERVER_ICONS: Record<string, string> = {
  github: "🐙", postgres: "🐘", filesystem: "🗂️",
  slack: "💬", notion: "📝", "brave-search": "🔍",
};
```

- [ ] **Step 2: 更新 `ToolCallCard` 以处理 `mcp_call`**

在 `ToolCallCard` 函数开头，替换 `type` 和 `summary` 的计算：

```tsx
function ToolCallCard({ toolCall }: { toolCall: ToolCall }) {
  const [open, setOpen] = useState(false);

  // mcp_call 特殊处理：展示内层 server · tool
  const isMcp = toolCall.name === "mcp_call";
  const mcpServer = isMcp ? String(toolCall.args.server ?? "") : "";
  const mcpTool   = isMcp ? String(toolCall.args.tool ?? "") : "";
  const mcpArgs   = isMcp ? (toolCall.args.arguments ?? {}) as Record<string, unknown> : toolCall.args;

  const displayName = isMcp ? `${mcpServer} · ${mcpTool}` : toolCall.name;
  const displayArgs = isMcp ? mcpArgs : toolCall.args;
  const displayIcon = isMcp
    ? (MCP_SERVER_ICONS[mcpServer] ?? "🔌")
    : (TOOL_TYPES[TOOL_CATEGORY[toolCall.name] ?? "read"]?.icon ?? "🔧");

  const type = isMcp
    ? { ...TOOL_TYPES.read, label: mcpServer || "MCP", bar: "bg-violet-500",
        badge: "bg-violet-100 dark:bg-violet-950", badgeText: "text-violet-700 dark:text-violet-300",
        cardBg: "bg-[#faf8ff] dark:bg-[#110f1f]", cardBorder: "border-violet-100 dark:border-violet-900/50" }
    : getToolType(toolCall.name);

  const summary = isMcp
    ? `${mcpTool}(${Object.keys(mcpArgs).join(", ")})`
    : getArgsSummary(toolCall.name, toolCall.args);
```

将 header 行的工具名展示替换为：

```tsx
          {/* Type badge */}
          <span className={`text-[9.5px] font-bold px-1.5 py-0.5 rounded-md flex-shrink-0 ${type.badge} ${type.badgeText} uppercase tracking-wide`}>
            {isMcp ? "MCP" : type.label}
          </span>

          {/* Tool name / icon */}
          <span className="text-[11px] flex-shrink-0">{displayIcon}</span>
          <span className="font-mono text-[11.5px] font-semibold text-[#1e293b] dark:text-[#d0d0d0] flex-shrink-0">
            {displayName}
          </span>
```

将展开体的参数展示从 `toolCall.args` 改为 `displayArgs`：

```tsx
        {isDiff ? (
          <DiffView args={displayArgs} path={...} />
        ) : (
          <pre ...>{JSON.stringify(displayArgs, null, 2)}</pre>
        )}
```

- [ ] **Step 3: TypeScript 检查**

```bash
npx tsc --noEmit 2>&1
```

期望: 无报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/Chat/ChatMessage.tsx
git commit -m "feat(mcp): render mcp_call tool cards with server icon and inner args"
```

---

## Task 12: 前端 — MCP 页面「发现工具」按钮

**文件：**
- 修改: `frontend/src/pages/CustomizeMcpPage.tsx`
- 修改: `frontend/src/api/mcp.ts`

- [ ] **Step 1: 在 `api/mcp.ts` 加两个函数**

```typescript
export const reloadServers = (): Promise<{ status: string; servers: string[] }> =>
  fetch(`${BASE}/reload`, { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

export const getDiscoveredTools = (): Promise<Record<string, Array<{ name: string; description: string }>>> =>
  fetch(`${BASE}/tools`).then((r) => r.json());
```

- [ ] **Step 2: 在 `CustomizeMcpPage.tsx` 加发现工具逻辑**

在 `CustomizeMcpPage` 函数顶部 state 区加：

```tsx
const [discovering, setDiscovering] = useState(false);
```

新增 `discoverTools` 函数：

```tsx
const discoverTools = async () => {
  setDiscovering(true);
  try {
    await reloadServers();
    await refresh();  // 刷新 SWR，工具列表会更新
  } catch (e) {
    console.error("Discover tools failed:", e);
  } finally {
    setDiscovering(false);
  }
};
```

在工具列表 Tab 的 `tools-header` div 中，「添加工具」按钮旁加：

```tsx
<button
  onClick={discoverTools}
  disabled={discovering}
  className="flex items-center gap-1.5 text-[11.5px] text-[#1e90ff] hover:text-[#1070cc] transition-colors disabled:opacity-40"
>
  <svg className={`w-3 h-3 ${discovering ? "animate-spin" : ""}`} viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M13.5 8A5.5 5.5 0 112.5 8" strokeLinecap="round"/>
    <path d="M13.5 4v4h-4"/>
  </svg>
  {discovering ? "发现中…" : "发现工具"}
</button>
```

在 import 顶部加：

```tsx
import { listServers, createServer, patchServer, deleteServer, reloadServers } from "@/api/mcp";
```

- [ ] **Step 3: TypeScript 检查**

```bash
npx tsc --noEmit 2>&1
```

期望: 无报错。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/mcp.ts frontend/src/pages/CustomizeMcpPage.tsx
git commit -m "feat(mcp): add discover tools button with reload API integration"
```

---

## 验证端到端流程

- [ ] **Step 1: 启动后端**

```bash
cd backend
uv run uvicorn choreo.gateway.app:app --reload
```

日志中应看到（若无 enabled MCP server 则跳过连接步骤）：
```
INFO: McpManager started
```

- [ ] **Step 2: 前端访问 /customize/mcp**

添加一个 GitHub MCP server（使用 stdio，命令 `npx -y @modelcontextprotocol/server-github`），点击「发现工具」，确认工具列表被填充。

- [ ] **Step 3: 测试 Agent 调用**

在聊天中发送消息（如"用 GitHub MCP 列出我的仓库"），确认：
1. System prompt 中出现 `Available MCP Tools` 段落
2. Agent 调用 `mcp_call` 工具
3. 若 approval=confirm → 出现 ReviewPanel 确认界面，显示 `🐙 github · list_repositories`
4. 用户确认后工具执行并返回结果

---

## 自检清单

- [x] `McpManager.start()` 连接失败不阻断 lifespan
- [x] `mcp_call` 是 Agent 工具列表中唯一的 MCP 工具
- [x] `get_index()` 过滤 deny/disabled 工具
- [x] `McpApprovalMiddleware` 拦截 `mcp_call` 并检查 approval
- [x] interrupt 格式与现有 ReviewPanel 兼容（`action_requests` + `review_configs`）
- [x] ReviewPanel 正确展示 `server · tool` 格式和内层参数
- [x] `ToolCallCard` 展示 MCP server 图标和内层参数
- [x] `/api/mcp/reload` 重新发现工具并同步 DB
- [x] `/api/mcp/tools` 返回实时工具状态
- [x] `_sync_tools_to_db` 保留已有用户配置（不覆盖 approval 设置）
