# Choreo 项目指南

## 项目结构（当前实际）

```
Choreo/
├── backend/
│   └── choreo/
│       ├── gateway/
│       │   ├── app.py                  # FastAPI 入口（lifespan 管理）
│       │   └── routers/
│       │       ├── threads.py          # /threads/ CRUD + /messages + /state
│       │       ├── runs.py             # /threads/{tid}/runs/stream  SSE 流
│       │       ├── models.py           # /models/ 列表 + active
│       │       ├── tasks.py            # /api/tasks/ 定时任务
│       │       └── history.py         # /api/history/
│       ├── agents/
│       │   ├── choreo_agent.py         # create_choreo_agent(checkpointer)
│       │   ├── registry.py             # get_agent() / set_agent()
│       │   ├── tools/                  # @tool 工具（git, script, runner, notify）
│       │   └── middlewares/
│       │       ├── title.py            # TitleMiddleware（aafter_agent 生成标题）
│       │       ├── call_limit.py       # ModelCallLimitMiddleware
│       │       ├── model_selector.py   # ModelSelectorMiddleware（awrap_model_call）
│       │       └── human_in_loop.py    # store_decision / pop_decision
│       ├── sandbox/                    # 【待实现】可插拔沙箱层
│       ├── store/
│       │   └── thread_store.py         # ThreadStore（PostgreSQL）
│       ├── models/
│       │   ├── thread.py               # Thread、ThreadState
│       │   ├── run.py                  # RunInput（input, config, context）
│       │   └── patched_openai.py       # PatchedChatOpenAI（保留 reasoning_content）
│       ├── model_factory.py            # load_model(name) 从 config.yaml 实例化
│       ├── config.py                   # pydantic_settings（.env）
│       └── db.py                       # SQLAlchemy async + ThreadRow / TaskRow
├── frontend/
│   └── src/
│       ├── App.tsx                     # 路由：/chat, /chat/:threadId, /tasks, /history
│       ├── pages/
│       │   ├── ChatPage.tsx            # 支持 URL threadId 回显历史
│       │   ├── TaskListPage.tsx
│       │   └── HistoryPage.tsx
│       ├── components/
│       │   ├── Sidebar/Sidebar.tsx     # useSWR 拉线程列表（无轮询）
│       │   ├── Chat/ChatInput.tsx      # 含模型选择器下拉
│       │   ├── Chat/ChatMessage.tsx
│       │   ├── Topbar/Topbar.tsx
│       │   └── ReviewPanel/ReviewPanel.tsx
│       ├── hooks/
│       │   ├── useChat.ts              # sendMessage(text, context)，mutate THREADS_KEY
│       │   └── useReview.ts
│       └── store/
│           ├── chatStore.tsx           # messages, streaming, resetMessages()
│           └── reviewStore.tsx
└── config.yaml                         # 模型配置（active_model + models[]）
```

## 启动方式

```bash
# 后端（注意入口是 gateway/app.py）
cd backend && uv run uvicorn choreo.gateway.app:app --reload

# 前端
cd frontend && pnpm dev
```

---

## 当前 API 路由

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/threads/` | 列出所有线程（含 title、status） |
| POST | `/threads/` | 创建新线程 |
| GET | `/threads/{tid}/state` | 获取线程状态 |
| POST | `/threads/{tid}/state` | 提交 HITL 决策 |
| GET | `/threads/{tid}/messages` | 获取历史消息（从 LangGraph state） |
| POST | `/threads/{tid}/runs/stream` | 流式运行（SSE） |
| GET | `/models/` | 列出 config.yaml 中的模型 |
| GET | `/models/active` | 当前默认模型 |

---

## LangChain v1 核心 API 备忘

### 1. create_agent

```python
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

agent = create_agent(
    model=llm,
    tools=[tool1, tool2],
    system_prompt="...",
    middleware=[...],
    checkpointer=checkpointer,
)
```

**注意**：不接受 `.bind_tools()` 的预绑定模型，不接受 `ToolNode`。

---

### 2. AgentMiddleware 钩子

| 钩子 | 触发时机 | 注意 |
|------|---------|------|
| `before_model` / `abefore_model` | LLM 调用前 | |
| `after_model` / `aafter_model` | LLM 调用后 | |
| `wrap_model_call` / `awrap_model_call` | 包裹 LLM（可换模型）| 必须实现 async 版本 |
| `wrap_tool_call` / `awrap_tool_call` | 包裹工具调用 | |
| `before_agent` / `abefore_agent` | Agent 启动前 | |
| `after_agent` / `aafter_agent` | Agent 完成后 | |

**关键陷阱**：`Runtime` 对象**不含 `config`**，不能 `runtime.config`。
获取 thread_id 等 configurable 参数必须用：
```python
from langgraph.config import get_config
config = get_config()
thread_id = config.get("configurable", {}).get("thread_id")
```

---

### 3. ModelRequest（awrap_model_call 内可替换模型）

```python
class ModelSelectorMiddleware(AgentMiddleware):
    async def awrap_model_call(self, request, handler):
        config = get_config()
        model_name = (config.get("configurable") or {}).get("model_name")
        if model_name:
            request.model = _get_model(model_name)  # ModelRequest 非 frozen，可直接赋值
        return await handler(request)
```

---

### 4. HumanInTheLoopMiddleware

```python
HumanInTheLoopMiddleware(interrupt_on={
    "tool_name": {
        "description": "即将执行，请确认",
        "allowed_decisions": ["approve", "edit", "reject"],
    },
})
```

interrupt payload 在 `__interrupt__[0].value`：
```json
{
  "action_requests": [{"name": "...", "arguments": {...}}],
  "review_configs": [{"action_name": "...", "allowed_decisions": [...]}]
}
```

Resume：
```python
Command(resume={"decisions": [{"type": "approve"}]})
Command(resume={"decisions": [{"type": "reject", "message": "原因"}]})
Command(resume={"decisions": [{"type": "edit", "edited_action": {"name": "...", "args": {...}}}]})
```

---

### 5. 流式输出（SSE）

后端 `astream(version="v2", stream_mode=["updates", "messages"])` 直接序列化发出：

```python
# messages 事件：直接转发 AIMessageChunk 字段（不做 thinking 拆分）
# 只过滤 AIMessageChunk（必须！否则 AIMessage replay 会双发）
if not isinstance(token, AIMessageChunk):
    continue

await queue.put({
    "event": "messages",
    "data": [{"content": token.content, "additional_kwargs": token.additional_kwargs}],
})
```

前端解析（`useChat.ts`）：
```ts
// DeepSeek R1: additional_kwargs.reasoning_content
// Claude: content 为 list，block.type === "thinking"
// 普通文本: content 为 string
```

---

### 6. RunInput 模型

```python
class RunInput(BaseModel):
    input: dict | None = None   # None 表示从 interrupt 恢复
    config: dict = {}
    context: dict = {}          # 自定义参数，合入 config["configurable"]
```

`context` 支持的 key：
- `model_name`：指定本次使用的模型（ModelSelectorMiddleware 读取）
- `sandbox_name`：【待实现】指定本次使用的沙箱
- `workspace_dir`：【待实现】指定工作目录

---

### 7. 模型工厂（model_factory.py）

```yaml
# config.yaml
active_model: deepseek-chat

models:
  - name: deepseek-chat
    use: choreo.models.patched_openai:PatchedChatOpenAI  # module:ClassName
    model: deepseek-chat
    api_key: $DEEPSEEK_API_KEY   # $ 开头从环境变量读取
    base_url: https://api.deepseek.com/v1
```

```python
from choreo.model_factory import load_model
llm = load_model()              # 读 active_model
llm = load_model("deepseek-reasoner")  # 指定名称
```

模型缓存在 `ModelSelectorMiddleware._model_cache` 里，首次加载后复用。

---

### 8. HITL 完整流程

```
前端发消息
  → POST /threads/{tid}/runs/stream {input: {messages: [...]}, context: {...}}
  → runs.py 合并 context 到 config["configurable"]
  → astream → HumanInTheLoopMiddleware interrupt
  → SSE event: updates, data: {__interrupt__: [{value: {action_requests, review_configs}}]}
  → 前端展示 ReviewPanel

用户审批
  → POST /threads/{tid}/state {values: {decisions: [{type: "approve"}]}}
  → store_decision(thread_id, decisions)
  → POST /threads/{tid}/runs/stream {input: null}
  → pop_decision → Command(resume=decision) → astream 继续
```

---

## 前端关键设计

### 线程列表（SWR，无轮询）

```ts
// Sidebar.tsx
const { data: threads } = useSWR(THREADS_KEY, fetcher, { revalidateOnFocus: true })

// useChat.ts - 两个触发点主动刷新
mutate(THREADS_KEY)  // 1. ensureThread() 创建新线程后
mutate(THREADS_KEY)  // 2. sendMessage finally（流结束后，标题已生成）
```

### 历史线程回显

- 路由 `/chat/:threadId` → ChatPage 从 URL 读 `threadId`
- 加载时并发请求 `/threads/{tid}/messages`（历史消息）
- SWR 缓存里的 threads 数据直接提供 title，无需单独请求
- `useChat(initialThreadId)` 初始化时绑定已有线程

### 模型选择器

- `ChatInput.tsx` 内嵌下拉，从 `/models/` 拉取列表
- 选中后在 `sendMessage(text, { model_name: selectedModel })` 传入
- 每次对话可以用不同模型，不影响 thread 存储

---

## 沙箱架构（待实现）

### 设计目标

参照 `model_factory.py` 模式，`config.yaml` 驱动多供应商沙箱，可扩展。

### config.yaml 扩展

```yaml
active_sandbox: local-dev

sandboxes:
  - name: local-dev
    provider: local
    workspace_dir: ./sandbox
    timeout: 120

  - name: docker-python
    provider: llm-sandbox    # pip install llm-sandbox[docker]
    backend: docker
    image: python:3.11
    timeout: 60

  - name: cloud-daytona
    provider: daytona         # pip install daytona
    api_key: $DAYTONA_API_KEY
    api_url: https://app.daytona.io/api
```

### BaseSandbox 接口

```python
class BaseSandbox(ABC):
    # 生命周期（一个 thread 一个 sandbox，多轮复用）
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def destroy(self) -> None: ...

    # 文件工具（对标 Claude Code）
    def read_file(self, path, offset=0, limit=2000) -> str: ...
    def write_file(self, path, content) -> str: ...
    def edit_file(self, path, old_string, new_string, replace_all=False) -> str: ...
    def list_dir(self, path=".") -> str: ...
    def grep(self, pattern, path=".", glob="**/*") -> str: ...

    # 命令执行（需 HITL 确认）
    async def bash(self, command, timeout=30) -> str: ...
```

### 目录结构

```
choreo/sandbox/
├── base.py              # BaseSandbox ABC
├── manager.py           # SandboxManager（thread_id → sandbox 注册表）
├── factory.py           # sandbox_factory(config_entry) → BaseSandbox
└── providers/
    ├── local.py         # LocalSandbox（subprocess + 路径白名单）
    ├── docker.py        # DockerSandbox（docker SDK）
    ├── llm_sandbox.py   # LLMSandboxAdapter
    └── daytona.py       # DaytonaSandboxAdapter
```

### 扩展新供应商

只需两步：
1. 在 `providers/` 下新建文件实现 `BaseSandbox`
2. 在 `factory.py` 的 `PROVIDERS` dict 加一行

其他代码（Manager、工具层、runs.py）完全不感知供应商。

### 路径安全（LocalSandbox）

```python
def _validate_path(self, path: str) -> Path:
    root = self._workspace.resolve()
    candidate = (root / path).resolve()
    if not str(candidate).startswith(str(root)):
        raise PermissionError(f"路径越界: {path}")
    return candidate
```

### SandboxManager 生命周期（集成到 FastAPI lifespan）

```python
# gateway/app.py lifespan
sandbox_manager = SandboxManager()
app.state.sandbox_manager = sandbox_manager
yield
await sandbox_manager.shutdown_all()

# runs.py
sandbox = await manager.acquire(thread_id, context.get("sandbox_name"))
# ... run ...
await manager.release(thread_id)
```

---

## 常见陷阱

| 问题 | 原因 | 解决 |
|------|------|------|
| middleware 里拿不到 thread_id | `Runtime` 不含 config | 用 `from langgraph.config import get_config` |
| title 一直为 null | TitleMiddleware 里用了 `runtime.config` | 改用 `get_config()` |
| 流式内容双发 | 没过滤 AIMessage replay | `if not isinstance(token, AIMessageChunk): continue` |
| `awrap_model_call` 报 NotImplementedError | 只实现了 sync 版本 | 必须实现 `async def awrap_model_call` |
| HITL 无法 resume | 无 checkpointer | `create_agent` 必须传 `checkpointer` |

---

## 包依赖

```toml
# backend/pyproject.toml
"langchain>=1.0"
"langchain-openai>=0.2"
"langchain-core>=0.3"
"langgraph>=0.2"
"langgraph-checkpoint-postgres"
"fastapi"
"sqlalchemy[asyncio]"
"asyncpg"
"psycopg[binary]"
"pydantic-settings"
"swr"  # 前端：pnpm add swr
```

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
