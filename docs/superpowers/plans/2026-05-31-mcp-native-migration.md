# MCP Native Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Choreo MCP 集成从 `langchain-mcp-adapters` 迁移到原生 `mcp` 包，并内置 LangChain Docs MCP 服务器。

**Architecture:** 重写 `McpManager`，用 `mcp.client.sse.sse_client` / `mcp.client.stdio.stdio_client` 替代 `MultiServerMCPClient`；工具发现和调用均通过 `ClientSession` 按需建立连接（无状态，每次 call 开 session 用完关掉）；引入轻量 `McpProxyTool` 类（非 LangChain BaseTool 子类）存储工具元数据并代理调用，保持 `_tool_registry` 接口不变；新增 `builtin.py` 在启动时将内置服务器 seed 进 DB。

**Tech Stack:** `mcp==1.27.2`（已通过传递依赖安装）、`mcp.client.sse`、`mcp.client.stdio`、`mcp.types`、FastAPI lifespan、SQLAlchemy async

---

## File Structure

| 文件 | 变更 |
|------|------|
| `backend/choreo/mcp/manager.py` | 完整重写：删除 `MultiServerMCPClient`，引入 `McpProxyTool` + `_open_session` |
| `backend/choreo/mcp/builtin.py` | 新建：内置服务器列表 + `seed_builtin_mcp_servers()` |
| `backend/choreo/gateway/app.py` | 新增：lifespan 里调用 `seed_builtin_mcp_servers()` |
| `backend/pyproject.toml` | 将 `mcp` 设为显式依赖，移除 `langchain-mcp-adapters` |
| `backend/tests/test_mcp_manager.py` | 更新：删除 `_client` 引用，改为 `_configs` |

---

### Task 1: 重写 `McpManager` 使用原生 `mcp` 包

**Files:**
- Modify: `backend/choreo/mcp/manager.py`
- Test: `backend/tests/test_mcp_manager.py`

- [ ] **Step 1: 更新测试——把 `_client` 引用改为 `_configs`**

打开 `backend/tests/test_mcp_manager.py`，将 `test_manager_reload_is_safe_when_no_servers` 中的断言改为：

```python
@pytest.mark.asyncio
async def test_manager_reload_is_safe_when_no_servers(monkeypatch):
    manager = McpManager()
    async def _no_servers(self):
        return {}
    monkeypatch.setattr(McpManager, "_load_configs", _no_servers)
    await manager.reload()
    assert manager._configs == {}  # 原来是 manager._client is None
```

- [ ] **Step 2: 运行测试，确认此测试当前 FAIL（因为 manager 还没改）**

```bash
cd backend && uv run pytest tests/test_mcp_manager.py::test_manager_reload_is_safe_when_no_servers -v
```

期望：FAIL（`McpManager` 还有 `_client` 属性，没有 `_configs`）

- [ ] **Step 3: 完整重写 `backend/choreo/mcp/manager.py`**

用以下代码完整替换该文件（305 行全部替换）：

```python
# backend/choreo/mcp/manager.py
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.types import TextContent

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
        self.args_schema = args_schema  # raw JSON Schema dict，兼容 manager._tool_signature
        self._server_name = server_name
        self._manager = manager

    async def ainvoke(self, arguments: dict) -> str:
        return await self._manager.call(self._server_name, self.name, arguments)


@asynccontextmanager
async def _open_session(config: dict):
    """按配置打开一个 MCP ClientSession，初始化后 yield，退出时自动关闭。"""
    transport = config["transport"]
    if transport == "stdio":
        params = StdioServerParameters(
            command=config["command"],
            args=config.get("args") or [],
            env=config.get("env") or None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    elif transport in ("sse", "http"):
        async with sse_client(config["url"]) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
    else:
        raise ValueError(f"Unsupported MCP transport: {transport}")


class McpManager:
    """无状态 MCP 连接管理器。每次工具调用按需打开 session，用完自动关闭。"""

    def __init__(self) -> None:
        # {server_name: config_dict}，替代原来的 _client
        self._configs: dict[str, dict] = {}
        # {server_name: {tool_name: McpProxyTool}}
        self._tool_registry: dict[str, dict[str, McpProxyTool]] = {}
        # {tool_name: server_name}，供 deny_interceptor 查 server
        self._tool_to_server: dict[str, str] = {}

    async def start(self) -> None:
        """lifespan 启动时调用：加载配置，发现工具，同步 DB。"""
        configs = await self._load_configs()
        if not configs:
            logger.info("No enabled MCP servers, skipping McpManager init.")
            return
        self._configs = configs
        await self._discover_all(list(configs.keys()))

    async def reload(self) -> None:
        """重新加载：从 DB 重读配置，重建工具注册表。"""
        self._configs = {}
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
        """返回指定工具的完整 JSON schema，过滤 deny/disabled 工具。"""
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

        return t.args_schema  # McpProxyTool.args_schema 已是 JSON Schema dict

    async def call(self, server: str, tool: str, arguments: dict) -> str:
        """打开新 session 调用工具，结果经过 deny 策略检查。"""
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
            async with _open_session(config) as session:
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
        """从 DB 读取 enabled MCP servers，构建配置字典。"""
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
        config = self._configs[server_name]

        async def _fetch_tools():
            async with _open_session(config) as session:
                result = await session.list_tools()
                return result.tools

        try:
            mcp_tools = await asyncio.wait_for(_fetch_tools(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("Tool discovery for '%s' timed out (15s).", server_name)
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
                    new_config[t.name] = existing[t.name]
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
        for key in ("anyOf", "oneOf"):
            variants = prop.get(key, [])
            non_null = [v for v in variants if v.get("type") != "null"]
            if non_null:
                return McpManager._json_type_hint(non_null[0])
        return "any"

    def _tool_signature(self, t: McpProxyTool) -> str:
        """Build 'tool_name(param: type, optional?: type)' from tool schema."""
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
```

- [ ] **Step 4: 运行全部 MCP 测试，确认通过**

```bash
cd backend && uv run pytest tests/test_mcp_manager.py -v
```

期望：所有 7 个测试 PASS。

注意：`test_sync_to_db_preserves_user_config` 使用 `fake_tool.name = "old_tool"`（MagicMock），`McpProxyTool` 改变不影响此测试，因为测试直接传 MagicMock。

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/mcp/manager.py backend/tests/test_mcp_manager.py
git commit -m "refactor(mcp): replace langchain-mcp-adapters with native mcp package"
```

---

### Task 2: 新增 `builtin.py`，内置 LangChain Docs MCP

**Files:**
- Create: `backend/choreo/mcp/builtin.py`
- Modify: `backend/choreo/gateway/app.py`

- [ ] **Step 1: 写 `builtin.py` 的测试（mock DB）**

在 `backend/tests/test_mcp_manager.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_seed_builtin_mcp_servers_idempotent(monkeypatch):
    """seed 两次不应创建重复行。"""
    from choreo.mcp.builtin import seed_builtin_mcp_servers
    from unittest.mock import AsyncMock, MagicMock

    added_rows = []

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(side_effect=lambda model, key: None)  # 假装都不存在
    mock_session.add = MagicMock(side_effect=lambda row: added_rows.append(row))
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("choreo.db.SessionLocal", MagicMock(return_value=mock_session))

    await seed_builtin_mcp_servers()
    first_count = len(added_rows)
    assert first_count >= 1  # 至少添加了 langchain-docs

    # 第二次调用：mock get 返回已存在的行（不应再 add）
    mock_session.get = AsyncMock(return_value=MagicMock())
    added_rows.clear()
    await seed_builtin_mcp_servers()
    assert len(added_rows) == 0  # 幂等，不重复添加
```

- [ ] **Step 2: 运行测试，确认 FAIL（builtin.py 未创建）**

```bash
cd backend && uv run pytest tests/test_mcp_manager.py::test_seed_builtin_mcp_servers_idempotent -v
```

期望：FAIL with `ModuleNotFoundError: No module named 'choreo.mcp.builtin'`

- [ ] **Step 3: 创建 `backend/choreo/mcp/builtin.py`**

```python
# backend/choreo/mcp/builtin.py
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

BUILTIN_SERVERS = [
    {
        "name": "langchain-docs",
        "transport": "sse",
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
                continue  # 已存在，不覆盖用户修改
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
```

- [ ] **Step 4: 运行测试，确认 PASS**

```bash
cd backend && uv run pytest tests/test_mcp_manager.py::test_seed_builtin_mcp_servers_idempotent -v
```

期望：PASS

- [ ] **Step 5: 在 `app.py` lifespan 里调用 `seed_builtin_mcp_servers`**

打开 `backend/choreo/gateway/app.py`，在 `from choreo.mcp import McpManager, set_mcp_manager` 行后添加 import，并在 lifespan 里 McpManager 初始化之前调用 seed：

```python
# 在文件顶部 import 区域添加：
from choreo.mcp.builtin import seed_builtin_mcp_servers

# lifespan 函数里，在 mcp_manager = McpManager() 行之前插入：
await seed_builtin_mcp_servers()
```

完整修改后 lifespan 顺序：
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

    # 1. 建表（幂等）
    await init_db()

    # 2. Seed 内置 MCP 服务器（建表后执行）
    await seed_builtin_mcp_servers()

    # 3. 初始化 McpManager
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()

    # 4. 初始化 SandboxManager
    manager = SandboxManager()
    set_sandbox_manager(manager)
    eviction_task = asyncio.create_task(manager.evict_idle())

    # 5. 初始化 PostgreSQL checkpointer
    async with AsyncPostgresSaver.from_conn_string(
        settings.DATABASE_URL_PSYCOPG
    ) as checkpointer:
        await checkpointer.setup()
        set_agent(create_choreo_agent(checkpointer))
        yield

    eviction_task.cancel()
    try:
        await eviction_task
    except asyncio.CancelledError:
        pass
    await manager.shutdown_all()
```

注意：`seed_builtin_mcp_servers` 必须在 `init_db()` **之后**调用（确保表已存在）。

- [ ] **Step 6: 运行全部测试**

```bash
cd backend && uv run pytest tests/test_mcp_manager.py -v
```

期望：所有 8 个测试 PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/choreo/mcp/builtin.py backend/choreo/gateway/app.py backend/tests/test_mcp_manager.py
git commit -m "feat(mcp): add builtin.py with LangChain Docs MCP server, seed on startup"
```

---

### Task 3: 更新依赖，移除 `langchain-mcp-adapters`

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 更新 `pyproject.toml`**

将 `langchain-mcp-adapters>=0.2.2` 替换为 `mcp>=1.0`：

```toml
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]",
    "langchain>=0.3",
    "langchain-openai>=0.2",
    "langchain-core>=0.3",
    "langgraph>=0.2",
    "pydantic-settings>=2.0",
    "apscheduler>=3.10",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "httpx>=0.27",
    "pyyaml>=6.0.3",
    "greenlet>=3.5.1",
    "psycopg[binary,pool]>=3.3.4",
    "langgraph-checkpoint-postgres>=3.1.0",
    "daytona>=0.182.0",
    "agent-sandbox>=0.0.30",
    "docker>=7.1.0",
    "mcp>=1.0",
    "authlib>=1.3",
    "python-jose[cryptography]>=3.3",
]
```

- [ ] **Step 2: 同步依赖（uv 自动处理）**

```bash
cd backend && uv sync
```

期望：`langchain-mcp-adapters` 从环境中卸载，`mcp` 直接安装。若提示版本冲突，先确认 `mcp` 当前版本并固定 `mcp>=1.27`。

- [ ] **Step 3: 运行全部测试，确认无 import 错误**

```bash
cd backend && uv run pytest tests/ -v
```

期望：全部测试 PASS，无 `ImportError: langchain_mcp_adapters`。

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(deps): replace langchain-mcp-adapters with native mcp>=1.0"
```

---

## Self-Review

**Spec coverage 检查：**
- ✅ `langchain-mcp-adapters` → `mcp` 原生：Task 1 完整重写 `manager.py`
- ✅ 保持公共接口不变：`call()`, `get_schema()`, `get_index()`, `get_all_tools_info()`, `reload()` 签名均未变
- ✅ `_tool_registry` 结构不变（`{server_name: {tool_name: McpProxyTool}}`）
- ✅ `mcp_tool.py` 不需要改动（只调用 `McpManager` 接口）
- ✅ 内置 LangChain Docs：Task 2 创建 `builtin.py` + seed
- ✅ 移除旧依赖：Task 3

**Placeholder 检查：** 无 TBD/TODO，所有步骤含完整代码。

**类型一致性：** `McpProxyTool` 在 Task 1 定义，Task 2 的测试使用 MagicMock（不直接引用 `McpProxyTool`），`_sync_to_db` 接受 `list[McpProxyTool]` 但只访问 `.name`，与定义一致。
