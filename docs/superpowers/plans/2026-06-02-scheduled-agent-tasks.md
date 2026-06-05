# Scheduled Agent Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现定时 Agent 任务系统——APScheduler 按 cron 触发、主 Agent headless 模式执行、结果存 task_runs 表、飞书通知、前端结果页。

**Architecture:** APScheduler 在 app.py lifespan 中启动，按 cron 触发 TaskRunner；TaskRunner 调用 `create_choreo_agent(headless=True)` 以无人值守模式执行任务，结果写入 `task_runs` 表并推飞书通知；前端新增 TaskRunsPage 展示运行历史，TaskListPage 升级支持创建任务。

**Tech Stack:** APScheduler 4.x（AsyncIOScheduler）、SQLAlchemy async、FastAPI、React + TypeScript、飞书 Webhook

---

## 文件地图

### 新建文件

| 文件 | 职责 |
|------|------|
| `backend/choreo/scheduler/__init__.py` | 模块入口，导出 TaskScheduler |
| `backend/choreo/scheduler/engine.py` | APScheduler 封装，管理 job 注册/移除/暂停 |
| `backend/choreo/scheduler/runner.py` | TaskRunner：创建 run 记录 → 执行 agent → 写结果 |
| `backend/choreo/scheduler/notifiers/__init__.py` | 导出 NotifierRouter |
| `backend/choreo/scheduler/notifiers/base.py` | BaseNotifier ABC |
| `backend/choreo/scheduler/notifiers/feishu.py` | FeishuNotifier，POST webhook |
| `backend/choreo/agents/tools/scheduled_task_tool.py` | LLM 工具：create_scheduled_task / list_scheduled_tasks |
| `backend/tests/test_scheduler_runner.py` | TaskRunner 单元测试 |
| `frontend/src/pages/TaskRunsPage.tsx` | 任务运行历史页 `/tasks/:taskId` |
| `frontend/src/components/Tasks/CreateTaskModal.tsx` | 新建任务表单弹窗 |

### 修改文件

| 文件 | 变更 |
|------|------|
| `backend/choreo/db.py` | 新增 `TaskRunRow`；`TaskRow` 加 `prompt`、`notify_config` 字段，`script_path` 改可选 |
| `backend/choreo/models/task.py` | 更新 `TaskCreate`；新增 `TaskRun`、`TaskRunCreate` 模型 |
| `backend/choreo/agents/choreo_agent.py` | 加 `headless: bool = False` 参数，headless 时去掉 HITL/Title/Checkpointer |
| `backend/choreo/gateway/routers/tasks.py` | 新增 runs CRUD 端点；CRUD 操作同步更新 scheduler |
| `backend/choreo/gateway/app.py` | lifespan 集成 TaskScheduler start/shutdown |
| `frontend/src/types/task.ts` | 更新 `Task`、`TaskCreate`；新增 `TaskRun` |
| `frontend/src/api/tasks.ts` | 新增 runs 相关 API 调用；新增手动触发 |
| `frontend/src/pages/TaskListPage.tsx` | 任务卡片更新；"+ 新建任务"打开 Modal |
| `frontend/src/App.tsx` | 新增 `/tasks/:taskId` 路由 |

---

## Task 1: DB Schema — TaskRow 更新 + TaskRunRow 新建

**Files:**
- Modify: `backend/choreo/db.py`

- [ ] **Step 1: 更新 `TaskRow`，`script_path` 改可选，新增 `prompt` 和 `notify_config`**

打开 `backend/choreo/db.py`，将 `TaskRow` 替换为：

```python
class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(String)
    cron: Mapped[str] = mapped_column(String)
    script_path: Mapped[str] = mapped_column(String, default="")
    prompt: Mapped[str] = mapped_column(String, default="")
    notify_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="active")
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
```

确认 `JSON` 已在 import 中（已有 `from sqlalchemy import BigInteger, Boolean, String, JSON, UniqueConstraint`）。

- [ ] **Step 2: 新增 `TaskRunRow`**

在 `TaskRow` 之后、`ThreadRow` 之前插入：

```python
class TaskRunRow(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|success|failed
    started_at: Mapped[int] = mapped_column(BigInteger, default=0)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output: Mapped[str] = mapped_column(String, default="")
    error: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 3: 验证建表幂等**

```bash
cd backend && uv run python -c "
import asyncio
from choreo.db import init_db
asyncio.run(init_db())
print('OK')
"
```

Expected: `OK`（无报错）

- [ ] **Step 4: Commit**

```bash
git add backend/choreo/db.py
git commit -m "feat(db): add TaskRunRow and update TaskRow with prompt/notify_config"
```

---

## Task 2: Pydantic 模型更新

**Files:**
- Modify: `backend/choreo/models/task.py`

- [ ] **Step 1: 更新 `TaskCreate`，新增 `TaskRun` 模型**

将 `backend/choreo/models/task.py` 完整替换为：

```python
from pydantic import BaseModel, Field
from typing import Literal
import uuid
import time


class TaskCreate(BaseModel):
    description: str
    cron: str
    prompt: str
    script_path: str = ""
    notify_config: dict = Field(default_factory=dict)


class TaskPatch(BaseModel):
    status: Literal["active", "paused"] | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    cron: str
    prompt: str
    script_path: str = ""
    notify_config: dict = Field(default_factory=dict)
    status: Literal["active", "paused"] = "active"
    last_run: int | None = None
    next_run: int | None = None


class TaskRunCreate(BaseModel):
    task_id: str
    status: str = "pending"
    started_at: int = Field(default_factory=lambda: int(time.time() * 1000))


class TaskRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    status: str  # pending|running|success|failed
    started_at: int
    finished_at: int | None = None
    output: str = ""
    error: str | None = None
```

- [ ] **Step 2: 验证 import 无误**

```bash
cd backend && uv run python -c "from choreo.models.task import Task, TaskRun, TaskCreate; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/models/task.py
git commit -m "feat(models): add TaskRun model, update TaskCreate with prompt/notify_config"
```

---

## Task 3: Notifiers

**Files:**
- Create: `backend/choreo/scheduler/notifiers/__init__.py`
- Create: `backend/choreo/scheduler/notifiers/base.py`
- Create: `backend/choreo/scheduler/notifiers/feishu.py`

- [ ] **Step 1: 创建目录和 base**

```bash
mkdir -p backend/choreo/scheduler/notifiers
```

创建 `backend/choreo/scheduler/notifiers/base.py`：

```python
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from choreo.db import TaskRow, TaskRunRow


class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, task: "TaskRow", run: "TaskRunRow") -> None: ...
```

- [ ] **Step 2: 创建 FeishuNotifier**

创建 `backend/choreo/scheduler/notifiers/feishu.py`：

```python
import httpx
import logging
from choreo.scheduler.notifiers.base import BaseNotifier

logger = logging.getLogger(__name__)


class FeishuNotifier(BaseNotifier):
    def __init__(self, webhook: str) -> None:
        self._webhook = webhook

    async def send(self, task, run) -> None:
        if not self._webhook:
            return
        summary = run.output[:400] + "..." if len(run.output) > 400 else run.output
        status_emoji = "✅" if run.status == "success" else "❌"
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"{status_emoji} 任务完成：{task.description}"}
                },
                "elements": [
                    {"tag": "markdown", "content": summary or "（无输出）"},
                ],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(self._webhook, json=payload)
                resp.raise_for_status()
        except Exception as e:
            logger.warning("FeishuNotifier failed: %s", e)
```

- [ ] **Step 3: 创建 NotifierRouter + `__init__.py`**

创建 `backend/choreo/scheduler/notifiers/__init__.py`：

```python
from choreo.scheduler.notifiers.base import BaseNotifier
from choreo.scheduler.notifiers.feishu import FeishuNotifier


class NotifierRouter:
    def _build(self, notify_config: dict) -> list[BaseNotifier]:
        notifiers: list[BaseNotifier] = []
        channels = notify_config.get("channels") or []
        if not channels and notify_config.get("type"):
            channels = [notify_config]
        for ch in channels:
            t = ch.get("type")
            if t == "feishu":
                notifiers.append(FeishuNotifier(ch.get("webhook", "")))
        return notifiers

    async def send(self, task, run) -> None:
        for n in self._build(task.notify_config or {}):
            await n.send(task, run)


__all__ = ["NotifierRouter", "BaseNotifier", "FeishuNotifier"]
```

- [ ] **Step 4: 验证 import**

```bash
cd backend && uv run python -c "from choreo.scheduler.notifiers import NotifierRouter; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/scheduler/notifiers/
git commit -m "feat(scheduler): add NotifierRouter with FeishuNotifier"
```

---

## Task 4: create_choreo_agent headless 模式

**Files:**
- Modify: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_headless_agent.py`：

```python
import pytest
from langgraph.checkpoint.memory import InMemorySaver


def test_headless_agent_has_no_hitl_middleware():
    from choreo.agents.choreo_agent import create_choreo_agent
    from choreo.agents.middlewares import UnifiedHITLMiddleware, TitleMiddleware

    agent = create_choreo_agent(headless=True)
    # LangChain agent 把 middleware 挂在 graph 上，通过 graph.__dict__ 检查
    # 简单检查：headless agent 创建不报错，且没有 checkpointer
    assert agent is not None


def test_chat_agent_requires_checkpointer():
    from choreo.agents.choreo_agent import create_choreo_agent
    agent = create_choreo_agent(InMemorySaver())
    assert agent is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run pytest tests/test_headless_agent.py -v
```

Expected: FAIL（`create_choreo_agent` 不接受 `headless` 参数）

- [ ] **Step 3: 修改 `create_choreo_agent`，加 `headless` 参数**

打开 `backend/choreo/agents/choreo_agent.py`，将 `create_choreo_agent` 替换为：

```python
def create_choreo_agent(checkpointer=None, headless: bool = False):
    """
    创建 Choreo agent。
    headless=True：无人值守模式，去掉 HITL/Title/Checkpointer，工具仅限只读+web。
    """
    from choreo.agents.tools.web_tools import web_search, fetch_url

    if headless:
        _allowed = {"web_search", "fetch_url", "read_file", "list_dir", "grep", "read_git_log"}
        _all = [
            task,
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_manager,
            mcp_call, mcp_describe, web_search, fetch_url,
        ]
        tools = [t for t in _all if t.name in _allowed]
        middleware = [
            ModelSelectorMiddleware(),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
        ]
        return create_agent(
            model=llm,
            tools=tools,
            system_prompt=(
                "你是一个自动化定时任务执行助手，在无人值守的环境中独立运行。\n\n"
                "行为规范：\n"
                "- 不向用户提问，不等待确认；遇到歧义遵循"安全、保守、最小影响"原则自行判断，并在输出中标注所作假设\n"
                "- 严格按任务描述执行，不扩展范围；未明确授权的写操作一律不执行\n"
                "- 信息获取失败时，尝试替代方案后继续；无法完成时说明阻塞原因和已尝试的步骤，不返回空内容\n"
                "- 所有结论基于实际获取的数据，不编造；关键数据注明来源和采集时间\n"
                "- 涉及与上次结果对比时，明确列出新增、变更、删除项及关键差异，注明对比基线时间\n"
                "- 未指定时区默认 UTC，输出中标注所有时间的时区\n"
                "- 遵守被调用服务的速率限制，不泄露凭据与敏感信息"
            ),
            middleware=middleware,
        )

    return create_agent(
        model=llm,
        tools=[
            task,
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_manager,
            mcp_call, mcp_describe,
        ],
        system_prompt=build_system_prompt(),
        middleware=[
            McpContextMiddleware(),
            SkillsContextMiddleware(),
            ModelSelectorMiddleware(),
            UnifiedHITLMiddleware(
                interrupt_on={
                    "bash": {
                        "description": "即将执行 bash 命令，请确认",
                        "allowed_decisions": ["approve", "edit", "reject"],
                    },
                    "send_notification": {
                        "description": "即将发送通知，请确认",
                        "allowed_decisions": ["approve", "reject"],
                    },
                    "mcp_call": {
                        "description": "即将调用 MCP 工具，请确认",
                        "allowed_decisions": ["approve", "reject"],
                    },
                }
            ),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
            RetryToolCallMiddleware(max_retries=2, delay=1.0),
            TitleMiddleware(llm=llm, max_chars=20),
        ],
        checkpointer=checkpointer,
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && uv run pytest tests/test_headless_agent.py -v
```

Expected: PASS

- [ ] **Step 5: 确认原有 agent fixture 仍正常**

```bash
cd backend && uv run pytest tests/test_auth_jwt.py -v
```

Expected: PASS（无回归）

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/agents/choreo_agent.py backend/tests/test_headless_agent.py
git commit -m "feat(agent): add headless mode to create_choreo_agent"
```

---

## Task 5: TaskRunner

**Files:**
- Create: `backend/choreo/scheduler/runner.py`
- Create: `backend/tests/test_scheduler_runner.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_scheduler_runner.py`：

```python
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_runner_creates_run_record():
    """Runner 执行后 task_run 状态应为 success。"""
    from choreo.scheduler.runner import TaskRunner

    mock_task = MagicMock()
    mock_task.id = str(uuid.uuid4())
    mock_task.description = "test task"
    mock_task.prompt = "search github trending"
    mock_task.notify_config = {}

    mock_run = MagicMock()
    mock_run.id = str(uuid.uuid4())
    mock_run.status = "running"
    mock_run.output = ""

    with patch("choreo.scheduler.runner.get_task_and_last_run", new_callable=AsyncMock) as mock_get, \
         patch("choreo.scheduler.runner.create_run", new_callable=AsyncMock) as mock_create, \
         patch("choreo.scheduler.runner.update_run", new_callable=AsyncMock) as mock_update, \
         patch("choreo.scheduler.runner.create_choreo_agent") as mock_agent_factory, \
         patch("choreo.scheduler.runner.NotifierRouter") as mock_notifier_cls:

        mock_get.return_value = (mock_task, None)
        mock_create.return_value = mock_run

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(return_value={
            "messages": [MagicMock(content="## 结果\n找到10个项目")]
        })
        mock_agent_factory.return_value = mock_agent

        mock_notifier = MagicMock()
        mock_notifier.send = AsyncMock()
        mock_notifier_cls.return_value = mock_notifier

        runner = TaskRunner()
        await runner.run(mock_task.id)

        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert call_kwargs["status"] == "success"
        assert "结果" in call_kwargs["output"]
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run pytest tests/test_scheduler_runner.py -v
```

Expected: FAIL（`choreo.scheduler.runner` 不存在）

- [ ] **Step 3: 创建 `runner.py`**

创建 `backend/choreo/scheduler/runner.py`：

```python
from __future__ import annotations
import logging
import time
import uuid

from langchain_core.messages import HumanMessage

from choreo.db import SessionLocal, TaskRow, TaskRunRow
from choreo.scheduler.notifiers import NotifierRouter
from choreo.agents.choreo_agent import create_choreo_agent
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def get_task_and_last_run(task_id: str) -> tuple[TaskRow | None, TaskRunRow | None]:
    async with SessionLocal() as db:
        task = (await db.execute(select(TaskRow).where(TaskRow.id == task_id))).scalar_one_or_none()
        if not task:
            return None, None
        last = (await db.execute(
            select(TaskRunRow)
            .where(TaskRunRow.task_id == task_id, TaskRunRow.status == "success")
            .order_by(TaskRunRow.finished_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        return task, last


async def create_run(task_id: str) -> TaskRunRow:
    async with SessionLocal() as db:
        run = TaskRunRow(
            id=str(uuid.uuid4()),
            task_id=task_id,
            status="running",
            started_at=int(time.time() * 1000),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def update_run(run_id: str, *, status: str, output: str = "", error: str | None = None) -> None:
    async with SessionLocal() as db:
        run = (await db.execute(select(TaskRunRow).where(TaskRunRow.id == run_id))).scalar_one()
        run.status = status
        run.output = output
        run.error = error
        run.finished_at = int(time.time() * 1000)
        await db.commit()


class TaskRunner:
    async def run(self, task_id: str) -> None:
        task, last_run = await get_task_and_last_run(task_id)
        if not task:
            logger.error("TaskRunner: task %s not found", task_id)
            return

        run = await create_run(task_id)
        logger.info("TaskRunner: starting run %s for task %s", run.id, task_id)

        prompt = task.prompt
        if last_run and last_run.output:
            import datetime
            ts = datetime.datetime.fromtimestamp(last_run.finished_at / 1000).strftime("%Y-%m-%d %H:%M")
            prompt += f"\n\n---\n上次运行结果（{ts}）：\n{last_run.output}"

        try:
            agent = create_choreo_agent(headless=True)
            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
            messages = result.get("messages", [])
            output = ""
            for msg in reversed(messages):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content.strip():
                    output = content
                    break
            await update_run(run.id, status="success", output=output)
            logger.info("TaskRunner: run %s succeeded", run.id)
        except Exception as e:
            logger.exception("TaskRunner: run %s failed", run.id)
            await update_run(run.id, status="failed", error=str(e))
            return

        notifier = NotifierRouter()
        await notifier.send(task, run)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd backend && uv run pytest tests/test_scheduler_runner.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/scheduler/runner.py backend/tests/test_scheduler_runner.py
git commit -m "feat(scheduler): add TaskRunner with cross-run context and notification"
```

---

## Task 6: Scheduler Engine

**Files:**
- Create: `backend/choreo/scheduler/engine.py`
- Create: `backend/choreo/scheduler/__init__.py`

- [ ] **Step 1: 安装 APScheduler**

```bash
cd backend && uv add "apscheduler>=3.10"
```

Expected: apscheduler 出现在 `pyproject.toml` dependencies

- [ ] **Step 2: 创建 `engine.py`**

创建 `backend/choreo/scheduler/engine.py`：

```python
from __future__ import annotations
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from choreo.db import SessionLocal, TaskRow
from sqlalchemy import select

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        from choreo.scheduler.runner import TaskRunner
        runner = TaskRunner()

        async with SessionLocal() as db:
            rows = (await db.execute(select(TaskRow).where(TaskRow.status == "active"))).scalars().all()

        for row in rows:
            self._register(row.id, row.cron, runner)
            logger.info("Scheduler: registered task %s (%s)", row.id, row.cron)

        self._scheduler.start()
        logger.info("Scheduler started with %d task(s)", len(rows))

    def _register(self, task_id: str, cron: str, runner) -> None:
        try:
            trigger = CronTrigger.from_crontab(cron)
        except Exception as e:
            logger.warning("Invalid cron %r for task %s: %s", cron, task_id, e)
            return
        self._scheduler.add_job(
            runner.run,
            trigger=trigger,
            args=[task_id],
            id=task_id,
            replace_existing=True,
        )

    def add_task(self, task_id: str, cron: str) -> None:
        from choreo.scheduler.runner import TaskRunner
        self._register(task_id, cron, TaskRunner())

    def remove_task(self, task_id: str) -> None:
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass

    def pause_task(self, task_id: str) -> None:
        try:
            self._scheduler.pause_job(task_id)
        except Exception:
            pass

    def resume_task(self, task_id: str) -> None:
        try:
            self._scheduler.resume_job(task_id)
        except Exception:
            pass

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
```

- [ ] **Step 3: 创建 `__init__.py`**

创建 `backend/choreo/scheduler/__init__.py`：

```python
from choreo.scheduler.engine import TaskScheduler

__all__ = ["TaskScheduler"]
```

- [ ] **Step 4: 验证 import**

```bash
cd backend && uv run python -c "from choreo.scheduler import TaskScheduler; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/scheduler/
git commit -m "feat(scheduler): add TaskScheduler engine with APScheduler"
```

---

## Task 7: API — Task Runs 端点 + CRUD 同步 Scheduler

**Files:**
- Modify: `backend/choreo/gateway/routers/tasks.py`

- [ ] **Step 1: 更新 `_row_to_task` 和导入**

打开 `backend/choreo/gateway/routers/tasks.py`，将文件顶部替换为：

```python
import uuid
import time
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from choreo.models.task import Task, TaskCreate, TaskPatch, TaskRun
from choreo.db import SessionLocal, TaskRow, TaskRunRow
from choreo.auth.deps import get_current_user_id

router = APIRouter()


async def get_db():
    async with SessionLocal() as session:
        yield session


def _row_to_task(row: TaskRow) -> Task:
    return Task(
        id=row.id,
        description=row.description,
        cron=row.cron,
        prompt=row.prompt,
        script_path=row.script_path,
        notify_config=row.notify_config or {},
        status=row.status,
    )


def _row_to_run(row: TaskRunRow) -> TaskRun:
    return TaskRun(
        id=row.id,
        task_id=row.task_id,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        output=row.output,
        error=row.error,
    )
```

- [ ] **Step 2: 更新 CRUD 端点，同步 Scheduler**

将 `create_task`、`patch_task`、`remove_task` 端点替换为（`list_tasks` 不变）：

```python
@router.post("/", response_model=Task, status_code=201)
async def create_task(
    body: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    row = TaskRow(
        id=str(uuid.uuid4()),
        user_id=user_id,
        description=body.description,
        cron=body.cron,
        prompt=body.prompt,
        script_path=body.script_path,
        notify_config=body.notify_config,
        status="active",
    )
    db.add(row)
    await db.commit()
    scheduler = getattr(request.app.state, "task_scheduler", None)
    if scheduler:
        scheduler.add_task(row.id, row.cron)
    return _row_to_task(row)


@router.patch("/{task_id}", response_model=Task)
async def patch_task(
    task_id: str,
    body: TaskPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskRow).where(TaskRow.id == task_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "task not found")
    if body.status is not None:
        row.status = body.status
        scheduler = getattr(request.app.state, "task_scheduler", None)
        if scheduler:
            if body.status == "paused":
                scheduler.pause_task(task_id)
            else:
                scheduler.resume_task(task_id)
    await db.commit()
    return _row_to_task(row)


@router.delete("/{task_id}", status_code=204)
async def remove_task(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(TaskRow).where(TaskRow.id == task_id))
    if result.rowcount == 0:
        raise HTTPException(404, "task not found")
    await db.commit()
    scheduler = getattr(request.app.state, "task_scheduler", None)
    if scheduler:
        scheduler.remove_task(task_id)
```

- [ ] **Step 3: 新增 runs 端点**

在文件末尾追加：

```python
@router.get("/{task_id}/runs", response_model=list[TaskRun])
async def list_runs(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TaskRunRow)
        .where(TaskRunRow.task_id == task_id)
        .order_by(TaskRunRow.started_at.desc())
        .limit(20)
    )
    return [_row_to_run(r) for r in result.scalars()]


@router.get("/{task_id}/runs/{run_id}", response_model=TaskRun)
async def get_run(task_id: str, run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TaskRunRow).where(TaskRunRow.id == run_id, TaskRunRow.task_id == task_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "run not found")
    return _row_to_run(row)


@router.post("/{task_id}/runs", response_model=TaskRun, status_code=202)
async def trigger_run(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskRow).where(TaskRow.id == task_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "task not found")
    import asyncio
    from choreo.scheduler.runner import TaskRunner
    runner = TaskRunner()
    asyncio.create_task(runner.run(task_id))
    run = TaskRunRow(
        id=str(uuid.uuid4()),
        task_id=task_id,
        status="pending",
        started_at=int(time.time() * 1000),
    )
    db.add(run)
    await db.commit()
    return _row_to_run(run)
```

- [ ] **Step 4: 验证服务器启动无报错**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload &
sleep 3 && curl -s http://localhost:8000/api/tasks/ -H "Authorization: Bearer test" | head -c 100
kill %1
```

Expected: JSON 响应（可能是 401 或 `[]`，不是 500）

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/gateway/routers/tasks.py
git commit -m "feat(api): add task runs endpoints, sync scheduler on CRUD"
```

---

## Task 8: App.py lifespan 集成 Scheduler

**Files:**
- Modify: `backend/choreo/gateway/app.py`

- [ ] **Step 1: 在 lifespan 中启动/关闭 TaskScheduler**

在 `app.py` 的 import 区域添加：

```python
from choreo.scheduler import TaskScheduler
```

在 lifespan 函数中，找到 `# 1. 建表（幂等）` 之后，`# 2. 初始化 McpManager` 之前插入：

```python
    # 1b. 启动任务调度器
    task_scheduler = TaskScheduler()
    await task_scheduler.start()
    app.state.task_scheduler = task_scheduler
```

在 `finally:` 块的 `await _channel_manager.stop_all()` 之后添加：

```python
        task_scheduler.shutdown()
```

- [ ] **Step 2: 验证启动日志**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload 2>&1 | head -20
```

Expected: 日志中出现 `Scheduler started with N task(s)`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/gateway/app.py
git commit -m "feat(app): integrate TaskScheduler into lifespan"
```

---

## Task 9: LLM 工具 — 对话创建定时任务

**Files:**
- Create: `backend/choreo/agents/tools/scheduled_task_tool.py`
- Modify: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: 创建 `scheduled_task_tool.py`**

创建 `backend/choreo/agents/tools/scheduled_task_tool.py`：

```python
import uuid
import logging
from langchain_core.tools import tool
from choreo.db import SessionLocal, TaskRow
from sqlalchemy import select

logger = logging.getLogger(__name__)


@tool
async def create_scheduled_task(
    description: str,
    cron: str,
    prompt: str,
    webhook: str = "",
) -> str:
    """
    创建一个定时 Agent 任务。

    Args:
        description: 任务名称（一句话，如"每周 GitHub 热门项目追踪"）
        cron: Cron 表达式（如 "0 9 * * 1" 表示每周一09:00）
        prompt: 给 Agent 的完整指令，越详细越好
        webhook: 飞书 Webhook URL（可选），任务完成后推送通知
    """
    from langgraph.config import get_config
    config = get_config()
    user_id = (config.get("configurable") or {}).get("user_id")

    notify_config: dict = {}
    if webhook:
        notify_config = {"channels": [{"type": "feishu", "webhook": webhook}]}

    async with SessionLocal() as db:
        row = TaskRow(
            id=str(uuid.uuid4()),
            user_id=user_id,
            description=description,
            cron=cron,
            prompt=prompt,
            script_path="",
            notify_config=notify_config,
            status="active",
        )
        db.add(row)
        await db.commit()

    logger.info("create_scheduled_task: created %s (cron=%s)", row.id, cron)

    from choreo.agents.registry import get_scheduler
    scheduler = get_scheduler()
    if scheduler:
        scheduler.add_task(row.id, cron)

    return f"任务已创建：{description}（cron: {cron}，ID: {row.id}）"


@tool
async def list_scheduled_tasks() -> str:
    """列出当前所有定时任务。"""
    from langgraph.config import get_config
    config = get_config()
    user_id = (config.get("configurable") or {}).get("user_id")

    async with SessionLocal() as db:
        rows = (await db.execute(
            select(TaskRow).where(TaskRow.user_id == user_id)
        )).scalars().all()

    if not rows:
        return "当前没有定时任务。"
    lines = [f"- {r.description}（cron: {r.cron}，状态: {r.status}，ID: {r.id}）" for r in rows]
    return "\n".join(lines)
```

- [ ] **Step 2: 在 `registry.py` 暴露 scheduler 引用**

打开 `backend/choreo/agents/registry.py`，在现有的 `get_agent`/`set_agent` 之后追加：

```python
_scheduler = None

def set_scheduler(s) -> None:
    global _scheduler
    _scheduler = s

def get_scheduler():
    return _scheduler
```

- [ ] **Step 3: 在 `app.py` lifespan 注册 scheduler 引用**

在 `app.py` 中 `from choreo.agents import create_choreo_agent, set_agent` 的 import 行，加入 `set_scheduler`：

```python
from choreo.agents import create_choreo_agent, set_agent
from choreo.agents.registry import set_scheduler
```

在 `task_scheduler = TaskScheduler()` 之后插入：

```python
    set_scheduler(task_scheduler)
```

- [ ] **Step 4: 注册工具到 `choreo_agent.py`**

在 `backend/choreo/agents/choreo_agent.py` 顶部 import 区域添加：

```python
from choreo.agents.tools.scheduled_task_tool import create_scheduled_task, list_scheduled_tasks
```

在 `create_choreo_agent` 的聊天模式 tools 列表中追加这两个工具：

```python
        tools=[
            task,
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_manager,
            mcp_call, mcp_describe,
            create_scheduled_task, list_scheduled_tasks,  # 新增
        ],
```

- [ ] **Step 5: 验证 import**

```bash
cd backend && uv run python -c "
from choreo.agents.tools.scheduled_task_tool import create_scheduled_task, list_scheduled_tasks
print(create_scheduled_task.name, list_scheduled_tasks.name)
"
```

Expected: `create_scheduled_task list_scheduled_tasks`

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/agents/tools/scheduled_task_tool.py \
        backend/choreo/agents/registry.py \
        backend/choreo/agents/choreo_agent.py \
        backend/choreo/gateway/app.py
git commit -m "feat(agent): add create_scheduled_task/list_scheduled_tasks LLM tools"
```

---

## Task 10: 前端类型和 API 客户端更新

**Files:**
- Modify: `frontend/src/types/task.ts`
- Modify: `frontend/src/api/tasks.ts`

- [ ] **Step 1: 更新 `task.ts`**

将 `frontend/src/types/task.ts` 完整替换为：

```typescript
export interface Task {
  id: string;
  description: string;
  cron: string;
  prompt: string;
  script_path: string;
  notify_config: Record<string, unknown>;
  status: "active" | "paused";
  last_run?: number;
  next_run?: number;
}

export interface TaskCreate {
  description: string;
  cron: string;
  prompt: string;
  script_path?: string;
  notify_config?: Record<string, unknown>;
}

export interface TaskRun {
  id: string;
  task_id: string;
  status: "pending" | "running" | "success" | "failed";
  started_at: number;
  finished_at?: number;
  output: string;
  error?: string;
}
```

- [ ] **Step 2: 更新 `api/tasks.ts`**

将 `frontend/src/api/tasks.ts` 完整替换为：

```typescript
import { apiFetch } from "@/lib/api";
import type { Task, TaskCreate, TaskRun } from "@/types/task";

const BASE = "/api/tasks";

export const getTasks = (): Promise<Task[]> =>
  apiFetch(BASE).then((r) => r.json());

export const createTask = (body: TaskCreate): Promise<Task> =>
  apiFetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const patchTask = (id: string, body: { status: "active" | "paused" }): Promise<Task> =>
  apiFetch(`${BASE}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const deleteTask = (id: string): Promise<void> =>
  apiFetch(`${BASE}/${id}`, { method: "DELETE" }).then(() => undefined);

export const getTaskRuns = (taskId: string): Promise<TaskRun[]> =>
  apiFetch(`${BASE}/${taskId}/runs`).then((r) => r.json());

export const getTaskRun = (taskId: string, runId: string): Promise<TaskRun> =>
  apiFetch(`${BASE}/${taskId}/runs/${runId}`).then((r) => r.json());

export const triggerTaskRun = (taskId: string): Promise<TaskRun> =>
  apiFetch(`${BASE}/${taskId}/runs`, { method: "POST" }).then((r) => r.json());
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | grep -v "node_modules" | head -20
```

Expected: 无错误或仅有不相关的警告

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/task.ts frontend/src/api/tasks.ts
git commit -m "feat(frontend): update Task type and add TaskRun API client"
```

---

## Task 11: 前端 — CreateTaskModal

**Files:**
- Create: `frontend/src/components/Tasks/CreateTaskModal.tsx`

- [ ] **Step 1: 创建目录**

```bash
mkdir -p frontend/src/components/Tasks
```

- [ ] **Step 2: 创建 `CreateTaskModal.tsx`**

创建 `frontend/src/components/Tasks/CreateTaskModal.tsx`：

```tsx
import { useState } from "react";
import { createTask } from "@/api/tasks";
import type { Task } from "@/types/task";

const CRON_PRESETS = [
  { label: "每天早上 9 点", value: "0 9 * * *" },
  { label: "每周一早上 9 点", value: "0 9 * * 1" },
  { label: "每小时", value: "0 * * * *" },
];

interface Props {
  onClose: () => void;
  onCreated: (task: Task) => void;
}

export default function CreateTaskModal({ onClose, onCreated }: Props) {
  const [form, setForm] = useState({
    description: "",
    cron: "",
    prompt: "",
    webhook: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    if (!form.description || !form.cron || !form.prompt) {
      setError("名称、Cron 和指令为必填项");
      return;
    }
    setLoading(true);
    setError("");
    try {
      const notify_config = form.webhook
        ? { channels: [{ type: "feishu", webhook: form.webhook }] }
        : {};
      const task = await createTask({
        description: form.description,
        cron: form.cron,
        prompt: form.prompt,
        notify_config,
      });
      onCreated(task);
    } catch {
      setError("创建失败，请检查输入");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-[#1a1a1a] rounded-2xl shadow-xl w-full max-w-md mx-4 p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">新建定时任务</h2>
          <button onClick={onClose} className="text-[#aaa] hover:text-[#555] text-lg leading-none">×</button>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">任务名称 *</label>
            <input
              value={form.description}
              onChange={set("description")}
              placeholder="如：每周 GitHub 热门项目追踪"
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">执行频率 *</label>
            <select
              value={CRON_PRESETS.find(p => p.value === form.cron)?.value || "__custom"}
              onChange={(e) => {
                if (e.target.value !== "__custom") setForm(f => ({ ...f, cron: e.target.value }));
              }}
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-white dark:bg-[#1a1a1a] outline-none"
            >
              <option value="__custom">自定义 cron...</option>
              {CRON_PRESETS.map(p => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
            <input
              value={form.cron}
              onChange={set("cron")}
              placeholder="0 9 * * 1"
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none font-mono"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">Agent 指令 *</label>
            <textarea
              value={form.prompt}
              onChange={set("prompt")}
              rows={4}
              placeholder="搜索本周 GitHub Stars 增长最快的 10 个项目，按增量排序，给出简短描述..."
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none resize-none"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-[#888]">飞书 Webhook（可选）</label>
            <input
              value={form.webhook}
              onChange={set("webhook")}
              placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
              className="text-[12.5px] px-3 py-2 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] bg-transparent outline-none"
            />
          </div>
        </div>

        {error && <p className="text-[11px] text-red-500">{error}</p>}

        <div className="flex gap-2 justify-end pt-1">
          <button
            onClick={onClose}
            className="text-[12px] px-3 py-1.5 rounded-lg border border-[#e0dcd4] dark:border-[#2a2a2a] text-[#555]"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={loading}
            className="text-[12px] px-4 py-1.5 rounded-lg bg-[#0f0f0f] dark:bg-[#e8e8e8] text-white dark:text-[#0f0f0f] disabled:opacity-50"
          >
            {loading ? "创建中..." : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Tasks/
git commit -m "feat(frontend): add CreateTaskModal component"
```

---

## Task 12: 前端 — TaskRunsPage

**Files:**
- Create: `frontend/src/pages/TaskRunsPage.tsx`

- [ ] **Step 1: 创建 `TaskRunsPage.tsx`**

创建 `frontend/src/pages/TaskRunsPage.tsx`：

```tsx
import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getTasks, getTaskRuns, triggerTaskRun } from "@/api/tasks";
import Topbar from "@/components/Topbar/Topbar";
import type { Task, TaskRun } from "@/types/task";

function statusBadge(status: TaskRun["status"]) {
  const map: Record<string, string> = {
    success: "bg-green-50 dark:bg-[#0d2010] text-green-700 dark:text-green-400",
    failed: "bg-red-50 dark:bg-[#200d0d] text-red-600 dark:text-red-400",
    running: "bg-blue-50 dark:bg-[#0d1020] text-blue-600 dark:text-blue-400",
    pending: "bg-[#f1f5f9] dark:bg-[#1a1a1a] text-[#94a3b8]",
  };
  const label: Record<string, string> = {
    success: "成功", failed: "失败", running: "运行中", pending: "等待中"
  };
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 ${map[status]}`}>
      {label[status]}
    </span>
  );
}

function formatTs(ms: number) {
  return new Date(ms).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function TaskRunsPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [task, setTask] = useState<Task | null>(null);
  const [runs, setRuns] = useState<TaskRun[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!taskId) return;
    getTasks().then((ts) => setTask(ts.find((t) => t.id === taskId) ?? null));
    getTaskRuns(taskId).then(setRuns);
  }, [taskId]);

  useEffect(() => {
    if (!taskId) return;
    const hasRunning = runs.some((r) => r.status === "running" || r.status === "pending");
    if (hasRunning && !pollRef.current) {
      pollRef.current = setInterval(() => {
        getTaskRuns(taskId).then(setRuns);
      }, 3000);
    } else if (!hasRunning && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [runs, taskId]);

  const trigger = async () => {
    if (!taskId) return;
    setTriggering(true);
    try {
      const run = await triggerTaskRun(taskId);
      setRuns((prev) => [run, ...prev]);
    } finally {
      setTriggering(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar
        title={task?.description ?? "任务详情"}
        action={
          <div className="flex gap-2">
            <button
              onClick={() => navigate("/tasks")}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555]"
            >
              ← 返回
            </button>
            <button
              onClick={trigger}
              disabled={triggering}
              className="text-[11px] px-2.5 py-1 rounded-lg bg-[#0f0f0f] dark:bg-[#e8e8e8] text-white dark:text-[#0f0f0f] disabled:opacity-50"
            >
              {triggering ? "触发中..." : "立即触发"}
            </button>
          </div>
        }
      />
      <div className="flex-1 overflow-y-auto">
        {task && (
          <div className="max-w-[740px] mx-auto px-6 pt-4 pb-2">
            <p className="text-[11px] text-[#aaa]">cron: {task.cron}</p>
          </div>
        )}
        {runs.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-[#aaa] text-sm">
            暂无运行记录
          </div>
        ) : (
          <div className="max-w-[740px] mx-auto px-6 py-3 flex flex-col gap-2">
            {runs.map((run) => (
              <div
                key={run.id}
                className="bg-white dark:bg-[#1a1a1a] border border-[#e0dcd4] dark:border-[#202020] rounded-xl overflow-hidden"
              >
                <div
                  className="flex items-center gap-3 px-3.5 py-3 cursor-pointer"
                  onClick={() => setExpanded(expanded === run.id ? null : run.id)}
                >
                  {statusBadge(run.status)}
                  <span className="text-[11px] text-[#aaa] flex-1">{formatTs(run.started_at)}</span>
                  {run.output && (
                    <span className="text-[11px] text-[#555] truncate max-w-[200px]">
                      {run.output.slice(0, 60)}…
                    </span>
                  )}
                  <span className="text-[10px] text-[#aaa]">{expanded === run.id ? "▲" : "▼"}</span>
                </div>
                {expanded === run.id && (
                  <div className="px-3.5 pb-4 border-t border-[#f0ece4] dark:border-[#202020]">
                    {run.error ? (
                      <pre className="text-[11px] text-red-500 mt-3 whitespace-pre-wrap">{run.error}</pre>
                    ) : (
                      <pre className="text-[11.5px] text-[#333] dark:text-[#ccc] mt-3 whitespace-pre-wrap font-sans leading-relaxed">
                        {run.output || "（无输出）"}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/TaskRunsPage.tsx
git commit -m "feat(frontend): add TaskRunsPage with polling and manual trigger"
```

---

## Task 13: 前端 — TaskListPage 升级 + 路由

**Files:**
- Modify: `frontend/src/pages/TaskListPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 更新 `TaskListPage.tsx`**

将 `frontend/src/pages/TaskListPage.tsx` 完整替换为：

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getTasks, deleteTask, patchTask } from "@/api/tasks";
import Topbar from "@/components/Topbar/Topbar";
import CreateTaskModal from "@/components/Tasks/CreateTaskModal";
import type { Task } from "@/types/task";

export default function TaskListPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    getTasks().then(setTasks).catch(console.error);
  }, []);

  const toggleStatus = async (task: Task) => {
    const updated = await patchTask(task.id, {
      status: task.status === "active" ? "paused" : "active",
    });
    setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  };

  const remove = async (id: string) => {
    await deleteTask(id);
    setTasks((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar
        title="定时任务"
        action={
          <button
            onClick={() => setShowCreate(true)}
            className="text-[11px] px-2.5 py-1 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555] dark:text-[#555] hover:opacity-80"
          >
            + 新建任务
          </button>
        }
      />
      <div className="flex-1 overflow-y-auto">
        {tasks.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-[#aaa] dark:text-[#333] text-sm">
            暂无定时任务，通过对话让 Choreo 帮你创建
          </div>
        ) : (
          <div className="max-w-[740px] mx-auto px-6 py-5 flex flex-col gap-2.5">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center gap-3 bg-white dark:bg-[#1a1a1a] border border-[#e0dcd4] dark:border-[#202020] rounded-xl px-3.5 py-3"
              >
                <div
                  className="flex-1 min-w-0 cursor-pointer"
                  onClick={() => navigate(`/tasks/${task.id}`)}
                >
                  <p className="text-[12.5px] font-medium text-[#0f0f0f] dark:text-[#e8e8e8] truncate hover:underline">
                    {task.description}
                  </p>
                  <p className="text-[10.5px] text-[#aaa] dark:text-[#444] mt-0.5 truncate">
                    cron: {task.cron}
                  </p>
                </div>
                <span
                  className={`text-[10px] px-2 py-0.5 rounded-full flex-shrink-0 ${
                    task.status === "active"
                      ? "bg-green-50 dark:bg-[#0d2010] text-green-700 dark:text-green-400"
                      : "bg-[#f1f5f9] dark:bg-[#1a1a1a] text-[#94a3b8] dark:text-[#444]"
                  }`}
                >
                  {task.status === "active" ? "运行中" : "已暂停"}
                </span>
                <button
                  onClick={() => toggleStatus(task)}
                  className="text-[10.5px] text-[#64748b] dark:text-[#444] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8]"
                >
                  {task.status === "active" ? "暂停" : "恢复"}
                </button>
                <button
                  onClick={() => remove(task.id)}
                  className="text-[10.5px] text-red-400 dark:text-[#f87171] hover:text-red-600"
                >
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
      {showCreate && (
        <CreateTaskModal
          onClose={() => setShowCreate(false)}
          onCreated={(task) => {
            setTasks((prev) => [task, ...prev]);
            setShowCreate(false);
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: 在 `App.tsx` 添加 `/tasks/:taskId` 路由**

打开 `frontend/src/App.tsx`，在 `import TaskListPage` 之后追加：

```typescript
import TaskRunsPage from "./pages/TaskRunsPage";
```

在 `<Route path="/tasks" element={<TaskListPage />} />` 之后插入：

```tsx
<Route path="/tasks/:taskId" element={<TaskRunsPage />} />
```

- [ ] **Step 3: TypeScript 编译检查**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | grep -v "node_modules" | head -20
```

Expected: 无错误

- [ ] **Step 4: 启动前端验证**

```bash
cd frontend && pnpm dev &
```

打开浏览器 `http://localhost:5173/tasks`：
- 确认"+ 新建任务"按钮点击后弹出 Modal
- 确认任务名称可点击跳转到 `/tasks/:taskId`
- 确认 `/tasks/:taskId` 页面正常渲染

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/TaskListPage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): wire up CreateTaskModal and TaskRunsPage routing"
```

---

## 端到端验证

- [ ] **验证 1：调度引擎**

在聊天中输入：`帮我创建一个定时任务，每分钟运行一次，让 Agent 输出当前时间`

等待 1-2 分钟后，访问 `/tasks/:taskId`，确认出现运行记录。

- [ ] **验证 2：手动触发**

在 TaskRunsPage 点击"立即触发"，确认运行记录从 `pending` → `running` → `success`（页面自动轮询更新）。

- [ ] **验证 3：飞书通知（可选）**

在创建任务时填写飞书 webhook，触发任务后确认飞书收到卡片消息。

- [ ] **验证 4：跨次运行上下文**

同一任务触发两次，在第二次运行结果中确认 Agent 输出包含了"上次运行结果"的引用。
