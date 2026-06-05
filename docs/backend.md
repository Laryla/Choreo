# 后端框架设计文档

## 技术栈

| 技术 | 版本要求 | 用途 |
|------|----------|------|
| Python | >= 3.10 | 运行环境 |
| FastAPI | ^0.110 | HTTP 服务，完全兼容 LangGraph Server 路径 |
| LangChain | ^0.2 | `create_tool_calling_agent`、Tool 定义、LLM 调用 |
| LangSmith | latest | 可选：Tracing & 离线评估 |
| APScheduler | ^3.10 | 定时任务调度 |
| gh CLI | latest | 读取 GitHub PR/issue |

> **架构说明**：后端是一个 FastAPI 服务，**API 路径和 SSE 事件格式完全对齐 LangGraph Server 规范**，因此前端可以直接使用 `@langchain/langgraph-sdk` 的 `Client` 对接，无需任何适配。Agent 底层用 LangChain `create_tool_calling_agent` + 自定义 `HumanInTheLoopMiddleware`/`ModelCallLimitMiddleware` 实现，不依赖 LangGraph。

---

## 目录结构

```
backend/
├── choreo/
│   ├── __init__.py
│   ├── api.py                # FastAPI 入口，注册所有路由
│   ├── agent.py              # create_tool_calling_agent + 中间件组装
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── human_in_loop.py  # HumanInTheLoopMiddleware
│   │   └── call_limit.py     # ModelCallLimitMiddleware
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── threads.py        # /threads 相关（兼容 LangGraph Server）
│   │   ├── runs.py           # /threads/{id}/runs 相关（含流式）
│   │   ├── tasks.py          # /api/tasks 定时任务 CRUD
│   │   └── history.py        # /api/history 运行历史
│   ├── models/
│   │   ├── __init__.py
│   │   ├── thread.py         # Thread Pydantic 模型
│   │   ├── run.py            # RunInput / RunStatus 模型
│   │   ├── task.py           # Task / TaskCreate / TaskPatch
│   │   └── history.py        # HistoryRecord
│   ├── store/
│   │   ├── __init__.py
│   │   └── thread_store.py   # 线程状态存储（SQLite）
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── git.py            # read_git_log
│   │   ├── script.py         # generate_script
│   │   ├── runner.py         # run_script（调用沙箱）
│   │   └── notify.py         # send_notification
│   ├── sandbox.py            # 脚本隔离执行
│   ├── scheduler.py          # APScheduler 定时任务
│   └── config.py             # 环境变量（pydantic-settings）
├── tasks/                    # 生成的脚本落盘目录
├── pyproject.toml
├── .env.example
└── .env
```

---

## Agent 定义（agent.py）

使用 `create_agent`（LangChain 新统一 API），中间件通过 `middleware=[]` 参数传入：

```python
from langchain.agents import create_agent
from choreo.tools import read_git_log, generate_script, run_script, send_notification
from choreo.middleware import HumanInTheLoopMiddleware, ModelCallLimitMiddleware
from choreo.config import settings

agent = create_agent(
    model=f"openai:{settings.CHOREO_MODEL}",   # 或 "deepseek:deepseek-chat"
    tools=[read_git_log, generate_script, run_script, send_notification],
    middleware=[
        HumanInTheLoopMiddleware(interrupt_tools={"run_script", "send_notification"}),
        ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
    ],
    system_message="你是 Choreo，一个开发自动化 Agent。理解用户的开发杂活需求，"
                   "生成可执行脚本，执行脚本和发送通知前必须等待用户确认。",
)
```

---

## 中间件

中间件继承 `AgentMiddleware`，通过 `create_agent(middleware=[...])` 注入，与 v3 streaming 原生兼容。

### HumanInTheLoopMiddleware（middleware/human_in_loop.py）

在写操作工具执行前暂停 agent，推送 `__interrupt__` 事件，等待 `/threads/{id}/state` 收到用户决策后恢复：

```python
import asyncio, uuid
from langchain.agents.middleware import AgentMiddleware

PENDING: dict[str, asyncio.Event] = {}
DECISIONS: dict[str, dict] = {}

class HumanInTheLoopMiddleware(AgentMiddleware):
    def __init__(self, interrupt_tools: set[str]):
        self.interrupt_tools = interrupt_tools

    async def before_tool_call(self, tool_name: str, tool_input: dict, **kwargs):
        """在目标工具执行前触发，暂停并等待用户决策。"""
        if tool_name not in self.interrupt_tools:
            return tool_input  # 非写操作工具，直接放行

        task_id = str(uuid.uuid4())
        # 将 __interrupt__ 写入 agent 状态，v3 streaming 会自动推给前端
        kwargs["emit"]({
            "__interrupt__": [{
                "value": {
                    "task_id": task_id,
                    "tool": tool_name,
                    "args": tool_input,
                }
            }]
        })

        gate = asyncio.Event()
        PENDING[task_id] = gate
        await gate.wait()

        decision = DECISIONS.pop(task_id, {"action": "approve"})
        if decision["action"] == "reject":
            raise ValueError(f"用户拒绝：{decision.get('reason', '')}")
        if decision["action"] == "edit":
            tool_input.update(decision.get("patch", {}))

        return tool_input  # approve / edit 后继续执行


def resolve_review(task_id: str, decision: dict):
    """由 POST /threads/{id}/state 调用，唤醒挂起的 Agent。"""
    DECISIONS[task_id] = decision
    gate = PENDING.pop(task_id, None)
    if gate:
        gate.set()
```

### ModelCallLimitMiddleware（middleware/call_limit.py）

```python
from langchain.agents.middleware import AgentMiddleware

class ModelCallLimitMiddleware(AgentMiddleware):
    def __init__(self, max_calls: int = 20):
        self.max_calls = max_calls
        self._count = 0

    async def before_model_call(self, messages, **kwargs):
        self._count += 1
        if self._count > self.max_calls:
            raise RuntimeError("超出最大 LLM 调用次数限制")
        return messages
```

---

## FastAPI 接口（兼容 LangGraph Server 路径）

### 应用入口（api.py）

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from choreo.routers import threads, runs, tasks, history
from choreo.scheduler import scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(title="Choreo API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# LangGraph Server 兼容路径
app.include_router(threads.router, prefix="/threads", tags=["threads"])
app.include_router(runs.router,    prefix="/threads", tags=["runs"])

# 业务接口
app.include_router(tasks.router,   prefix="/api/tasks",   tags=["tasks"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
```

---

### Thread 接口（routers/threads.py）

#### `POST /threads`

创建新对话线程，返回 thread_id。

```python
@router.post("/", response_model=Thread, status_code=201)
async def create_thread():
    thread = Thread(thread_id=str(uuid.uuid4()), created_at=now())
    await thread_store.save(thread)
    return thread
```

**响应**
```json
{ "thread_id": "abc-123", "created_at": 1704700800 }
```

#### `GET /threads/{thread_id}/state`

返回线程当前状态（消息历史 + 是否有待审阅项）。

```python
@router.get("/{thread_id}/state")
async def get_thread_state(thread_id: str):
    return await thread_store.get_state(thread_id)
```

#### `POST /threads/{thread_id}/state`

更新线程状态，用于传入人工审阅决策，唤醒挂起的 Agent。

```python
@router.post("/{thread_id}/state", status_code=200)
async def update_thread_state(thread_id: str, body: StateUpdate):
    # body.values 中包含 { task_id, action, patch?, reason? }
    resolve_review(body.values["task_id"], body.values)
    return {"ok": True}
```

**StateUpdate 模型（models/run.py）**

```python
from pydantic import BaseModel

class StateUpdate(BaseModel):
    values: dict  # { "task_id": "...", "action": "approve"|"edit"|"reject", "patch": {}, "reason": "" }

class RunInput(BaseModel):
    input: dict        # { "messages": [{"role": "user", "content": "..."}] }
    config: dict = {}  # 可选配置（session_id 等）
```

---

### Run（流式）接口（routers/runs.py）

#### 设计原则：Agent 跑在后台，SSE 只读队列

Agent 执行与 SSE 连接**解耦**：

1. `POST /threads/{id}/runs/stream` 收到请求后，立即把 agent 作为 **asyncio 后台任务**启动，agent 把事件写入**每个 run 独立的内存队列**
2. SSE 连接只负责从队列里读事件推给前端
3. 前端切换页面/断开连接，agent 继续跑，事件继续入队
4. 前端重新连接后，调用 `GET /threads/{id}/runs/{run_id}/stream` 重新订阅，从队列中读取未消费的事件

```python
import asyncio, json, uuid
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from choreo.agent import executor
from choreo.store.thread_store import thread_store

router = APIRouter()

# run_id → asyncio.Queue，存放待推送事件
RUN_QUEUES: dict[str, asyncio.Queue] = {}
```

#### `POST /threads/{thread_id}/runs/stream`

创建 run，启动后台 agent 任务，返回 SSE 流。

```python
@router.post("/{thread_id}/runs/stream")
async def stream_run(thread_id: str, body: RunInput):
    run_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    RUN_QUEUES[run_id] = queue

    history = await thread_store.get_messages(thread_id)
    # create_agent 直接接受 messages 列表，历史消息拼在前面
    inputs = {
        "messages": history + body.input["messages"],
    }

    # agent 跑在后台，不阻塞 SSE 连接
    asyncio.create_task(_run_agent(run_id, thread_id, inputs, queue))

    return StreamingResponse(
        _read_queue(run_id, queue),
        media_type="text/event-stream",
    )


async def _run_agent(run_id: str, thread_id: str, inputs: dict, queue: asyncio.Queue):
    """后台任务：执行 agent，把事件写入队列。客户端断开不影响执行。"""
    await queue.put({"type": "metadata", "run_id": run_id})

    try:
        # v3 streaming：typed projections，不再手动解析 event envelope
        stream = await agent.astream_events(inputs, version="v3")

        # 并发消费 messages 和 tool_calls 两个 projection
        async def consume_messages():
            async for message in stream.messages:
                async for delta in message.text:
                    await queue.put({"type": "messages", "content": [{"content": delta}]})
                # 检测 __interrupt__（HumanInTheLoopMiddleware 写入的审阅请求）
                full_msg = await message.output
                if hasattr(full_msg, "additional_kwargs"):
                    interrupt = full_msg.additional_kwargs.get("__interrupt__")
                    if interrupt:
                        await queue.put({"type": "updates", "__interrupt__": interrupt})

        async def consume_tool_calls():
            async for call in stream.tool_calls:
                await queue.put({
                    "type": "updates",
                    "tool_start": {"tool": call.tool_name, "args": call.input},
                })

        await asyncio.gather(consume_messages(), consume_tool_calls())

        # 最终 state 快照
        final = await stream.output
        last_msg = final["messages"][-1].content if final.get("messages") else ""
        await thread_store.append_message(thread_id, {"role": "assistant", "content": last_msg})
        await queue.put({"type": "values", "messages": [{"role": "assistant", "content": last_msg}]})

    except Exception as e:
        await queue.put({"type": "error", "message": str(e)})
    finally:
        await queue.put(None)  # 结束信号


async def _read_queue(run_id: str, queue: asyncio.Queue):
    """从队列读事件推给前端。
    只在收到 None（agent 真正完成）时才清理 queue，
    客户端断开不清理，确保重连后仍能订阅。
    """
    while True:
        item = await queue.get()
        if item is None:
            RUN_QUEUES.pop(run_id, None)  # agent 已完成，清理
            yield "data: [DONE]\n\n"
            break
        yield f"data: {json.dumps(item)}\n\n"
```

#### `GET /threads/{thread_id}/runs/{run_id}/stream`

前端重连后重新订阅同一个 run 的事件流（队列中未消费的事件会继续推送）。

```python
@router.get("/{thread_id}/runs/{run_id}/stream")
async def restream_run(thread_id: str, run_id: str):
    queue = RUN_QUEUES.get(run_id)
    if not queue:
        raise HTTPException(404, "run not found or already completed")
    return StreamingResponse(_read_queue(run_id, queue), media_type="text/event-stream")
```

**SSE 事件类型（与 LangGraph Server 一致）**

| type | 含义 |
|------|------|
| `metadata` | run 元信息（run_id） |
| `messages` | LLM token 增量 |
| `updates` | 工具调用状态 / `__interrupt__` 审阅请求 |
| `values` | 完整 state 快照（最终消息） |
| `[DONE]` | run 结束 |

---

### 定时任务接口（routers/tasks.py）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 新建任务 |
| PATCH | `/api/tasks/{id}` | 暂停/恢复 |
| DELETE | `/api/tasks/{id}` | 删除任务 |

```python
@router.get("/", response_model=list[Task])
async def list_tasks():
    return await get_tasks()

@router.post("/", response_model=Task, status_code=201)
async def create_task(body: TaskCreate):
    task = await save_task(body)
    add_job(task.id, task.cron, task.script_path)
    return task

@router.patch("/{task_id}", response_model=Task)
async def patch_task(task_id: str, body: TaskPatch):
    task = await get_task(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    pause_job(task_id) if body.status == "paused" else resume_job(task_id)
    return await update_task(task_id, body)

@router.delete("/{task_id}", status_code=204)
async def remove_task(task_id: str):
    remove_job(task_id)
    await delete_task(task_id)
```

---

### 运行历史接口（routers/history.py）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/history` | 历史列表（分页，支持 task_id 过滤） |
| GET | `/api/history/{id}/output` | 产物文件内容 |

```python
@router.get("/", response_model=dict)
async def list_history(page: int = 1, size: int = 20, task_id: str | None = None):
    return await get_history(page=page, size=size, task_id=task_id)

@router.get("/{run_id}/output", response_class=PlainTextResponse)
async def get_run_output(run_id: str):
    record = await get_history_record(run_id)
    if not record:
        raise HTTPException(404, "run not found")
    return Path(record.output_path).read_text()
```

---

## 接口汇总

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/threads` | 创建线程 |
| GET | `/threads/{id}/state` | 查询线程状态 |
| POST | `/threads/{id}/state` | 更新状态（传入审阅决策） |
| POST | `/threads/{id}/runs/stream` | 启动 run，agent 后台执行，返回 SSE 流 |
| GET | `/threads/{id}/runs/{run_id}/stream` | 重连订阅同一 run 的事件流 |
| GET | `/api/tasks` | 任务列表 |
| POST | `/api/tasks` | 新建任务 |
| PATCH | `/api/tasks/{id}` | 暂停/恢复任务 |
| DELETE | `/api/tasks/{id}` | 删除任务 |
| GET | `/api/history` | 运行历史（分页） |
| GET | `/api/history/{id}/output` | 产物内容 |

---

## 工具列表

| 工具 | 文件 | 需人工确认 | 说明 |
|------|------|-----------|------|
| `read_git_log` | `tools/git.py` | 否 | 调用 `gh` CLI 读取 commit/PR/issue |
| `generate_script` | `tools/script.py` | 否 | LLM 生成 Python 脚本，落盘到 `tasks/` |
| `run_script` | `tools/runner.py` | **是** | 在沙箱中执行脚本 |
| `send_notification` | `tools/notify.py` | **是** | 发送飞书 Webhook 或邮件 |

---

## 沙箱（sandbox.py）

```python
import subprocess
from choreo.config import settings

def run_in_sandbox(script_path: str) -> str:
    result = subprocess.run(
        ["python", script_path],
        capture_output=True, text=True,
        timeout=settings.CHOREO_SANDBOX_TIMEOUT,
        cwd=settings.CHOREO_SANDBOX_WORKDIR,
    )
    return result.stdout or result.stderr
```

---

## LangSmith（可选）

仅需配置环境变量，所有 LangChain 调用自动上报 trace，无需修改代码：

```ini
LANGSMITH_API_KEY=ls__xxxx
LANGSMITH_PROJECT=choreo-dev
LANGSMITH_TRACING=true
```

---

## 环境变量（.env.example）

```ini
# LLM
OPENAI_API_KEY=sk-xxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
CHOREO_MODEL=deepseek-chat
CHOREO_MAX_LLM_CALLS=20

# LangSmith（可选）
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=choreo-dev
LANGSMITH_TRACING=false

# 通知
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_USER=user@example.com
SMTP_PASSWORD=xxxx

# 沙箱
CHOREO_SANDBOX_TIMEOUT=120
CHOREO_SANDBOX_WORKDIR=./sandbox
```

---

## 开发启动

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
uvicorn choreo.api:app --reload --port 8000
# → http://localhost:8000
# → Swagger UI http://localhost:8000/docs
```
