# 用户画像自动更新 实现计划

> **致自动化执行者：** 必须使用子技能 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 按任务逐步实现。步骤使用复选框（`- [ ]`）语法追踪进度。

**目标：** 每周自动从 Claude Code 会话日志中合成用户画像（`wiki/user/profile.md`），让主 agent 通过 `kb_read("user/profile.md")` 读取并个性化其行为。

**架构：** 三层设计——（1）可扩展抽象基类（`BaseSourceAdapter`、`BaseCollector`），（2）具体的 `ClaudeCodeCollector`，调用 `claude-code-log` CLI 并读取 `sessions-index.json`，（3）`profiler.py` 编排层，收集数据后调用 `create_kb_agent()` 并由 agent 通过 `kb_write_wiki` 写出 `wiki/user/profile.md` 和 `wiki/user/recent-context.md`。配备定时后台循环和手动触发端点。

**技术栈：** Python asyncio、APScheduler（已在依赖中）、`claude-code-log` CLI（PyPI）、FastAPI、现有 `create_kb_agent()` + `kb_write_wiki` 工具。

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `backend/choreo/knowledge_sources/__init__.py` | 包标记 |
| 新建 | `backend/choreo/knowledge_sources/base.py` | `BaseSourceAdapter` 抽象基类 |
| 新建 | `backend/choreo/activity/__init__.py` | 包标记 |
| 新建 | `backend/choreo/activity/collectors/__init__.py` | 包标记 |
| 新建 | `backend/choreo/activity/collectors/base.py` | `BaseCollector` 抽象基类 |
| 新建 | `backend/choreo/activity/collectors/claude_code.py` | `ClaudeCodeCollector` 实现 |
| 新建 | `backend/choreo/kb/profile_prompt.py` | `USER_PROFILE_PROMPT` 模板 |
| 新建 | `backend/choreo/activity/profiler.py` | `collect_all()`、`update_profile()`、`start_profile_scheduler()` |
| 新建 | `backend/tests/test_activity.py` | 采集器和编排层的测试 |
| 修改 | `backend/choreo/config.py` | 新增 `ACTIVITY_PROFILE: dict` 字段 |
| 修改 | `backend/config.yaml` | 新增注释掉的 `activity_profile:` 示例节 |
| 修改 | `backend/pyproject.toml` | 新增 `claude-code-log` 依赖 |
| 修改 | `backend/choreo/gateway/routers/knowledge.py` | 新增 `POST /api/kb/update-profile` 端点 |
| 修改 | `backend/choreo/gateway/app.py` | lifespan 中启动/关闭画像调度器 |
| 修改 | `frontend/src/pages/KnowledgePage.tsx` | 新增「更新用户画像」按钮 |

---

## 任务 1：依赖与配置

**涉及文件：**
- 修改：`backend/pyproject.toml`
- 修改：`backend/choreo/config.py`
- 修改：`backend/config.yaml`

- [ ] **步骤 1：在 pyproject.toml 中添加 claude-code-log**

在 `backend/pyproject.toml` 的 `dependencies` 列表中（`markitdown[all]>=0.1` 之后）添加：

```toml
    "claude-code-log>=0.1",
```

- [ ] **步骤 2：在 config.py 中新增配置字段**

在 `backend/choreo/config.py` 的 `KNOWLEDGE_BASE_DIR` 行之后添加：

```python
    # 用户画像
    ACTIVITY_PROFILE: dict = {}
```

- [ ] **步骤 3：在 config.yaml 中新增示例节**

在 `backend/config.yaml` 末尾添加（注释掉，不自动激活）：

```yaml
# 用户画像（每周自动从行为信号合成 wiki/user/profile.md）
# activity_profile:
#   enabled: true
#   schedule: "0 9 * * 1"   # 每周一 09:00
#   lookback_days: 7
#   sources:
#     - type: claude_code_logs
```

- [ ] **步骤 4：安装依赖**

```bash
cd backend && uv add claude-code-log
```

预期：无报错，`claude-code-log` 出现在 `uv.lock` 中。

- [ ] **步骤 5：验证 CLI 可用**

```bash
cd backend && uv run claude-code-log --help
```

预期：打印包含 `--format`、`--detail`、`--compact` 的用法说明。

- [ ] **步骤 6：提交**

```bash
git add backend/pyproject.toml backend/uv.lock backend/choreo/config.py backend/config.yaml
git commit -m "feat(profiling): 添加 claude-code-log 依赖和 ACTIVITY_PROFILE 配置"
```

---

## 任务 2：BaseSourceAdapter 抽象基类

**涉及文件：**
- 新建：`backend/choreo/knowledge_sources/__init__.py`
- 新建：`backend/choreo/knowledge_sources/base.py`

- [ ] **步骤 1：创建包**

新建空文件 `backend/choreo/knowledge_sources/__init__.py`。

- [ ] **步骤 2：实现 BaseSourceAdapter**

新建 `backend/choreo/knowledge_sources/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSourceAdapter(ABC):
    """从外部知识来源拉取文档写入 KB raw/。"""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.name: str = config.get("name", type(self).__name__)

    @abstractmethod
    async def pull(self) -> list[tuple[str, str]]:
        """返回 (filename, markdown_content) 列表，写入 raw/。

        filename: 相对文件名，如 "feishu-wiki-my-page.md"
        markdown_content: 完整 Markdown 文本
        """
        ...
```

- [ ] **步骤 3：验证导入**

```bash
cd backend && uv run python -c "from choreo.knowledge_sources.base import BaseSourceAdapter; print('ok')"
```

预期：打印 `ok`。

- [ ] **步骤 4：提交**

```bash
git add backend/choreo/knowledge_sources/
git commit -m "feat(profiling): 添加 BaseSourceAdapter 抽象基类"
```

---

## 任务 3：BaseCollector 抽象基类

**涉及文件：**
- 新建：`backend/choreo/activity/__init__.py`
- 新建：`backend/choreo/activity/collectors/__init__.py`
- 新建：`backend/choreo/activity/collectors/base.py`

- [ ] **步骤 1：创建包**

新建两个空文件：
- `backend/choreo/activity/__init__.py`
- `backend/choreo/activity/collectors/__init__.py`

- [ ] **步骤 2：实现 BaseCollector**

新建 `backend/choreo/activity/collectors/base.py`：

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class BaseCollector(ABC):
    """收集指定时间之后的用户行为信号。"""

    @abstractmethod
    async def collect(self, since: datetime) -> str:
        """返回 `since` 之后的行为摘要（Markdown 格式字符串）。

        如无数据或采集器不可用，返回空字符串。
        不抛出异常——调用方期望优雅降级。
        """
        ...
```

- [ ] **步骤 3：验证导入**

```bash
cd backend && uv run python -c "from choreo.activity.collectors.base import BaseCollector; print('ok')"
```

预期：打印 `ok`。

- [ ] **步骤 4：提交**

```bash
git add backend/choreo/activity/
git commit -m "feat(profiling): 添加 BaseCollector 抽象基类"
```

---

## 任务 4：ClaudeCodeCollector

**涉及文件：**
- 新建：`backend/choreo/activity/collectors/claude_code.py`
- 新建：`backend/tests/test_activity.py`

- [ ] **步骤 1：编写失败测试**

新建 `backend/tests/test_activity.py`：

```python
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from choreo.activity.collectors.claude_code import ClaudeCodeCollector, _desensitize


class TestDesensitize:
    def test_脱敏_api_key(self):
        text = "OPENAI_API_KEY=sk-secret123"
        result = _desensitize(text)
        assert "sk-secret123" not in result
        assert "<redacted>" in result

    def test_脱敏_token(self):
        result = _desensitize("access_token: ghp_abc123")
        assert "ghp_abc123" not in result

    def test_保留正常文本(self):
        text = "## 实现了 markitdown 上传\n- 支持 PDF/DOCX"
        assert _desensitize(text) == text


class TestClaudeCodeCollector:
    @pytest.fixture
    def projects_dir(self, tmp_path):
        proj = tmp_path / "projects" / "my-project"
        proj.mkdir(parents=True)
        index = [
            {
                "session_id": "abc123",
                "summary": "实现了功能 X",
                "message_count": 42,
                "git_branch": "feat/x",
                "updated_at": (datetime.now() - timedelta(days=1)).timestamp(),
            }
        ]
        (proj / "sessions-index.json").write_text(json.dumps(index))
        return tmp_path / "projects"

    @pytest.mark.asyncio
    async def test_采集返回字符串(self, projects_dir):
        collector = ClaudeCodeCollector(claude_projects_dir=projects_dir)
        since = datetime.now() - timedelta(days=7)
        with patch(
            "choreo.activity.collectors.claude_code.ClaudeCodeCollector._run_cc_log",
            new=AsyncMock(return_value="## 会话\n\n做了一些工作"),
        ):
            result = await collector.collect(since)
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_无近期会话时返回空字符串(self, tmp_path):
        proj = tmp_path / "projects" / "old-project"
        proj.mkdir(parents=True)
        index = [{"session_id": "xyz", "updated_at": (datetime.now() - timedelta(days=30)).timestamp()}]
        (proj / "sessions-index.json").write_text(json.dumps(index))
        collector = ClaudeCodeCollector(claude_projects_dir=tmp_path / "projects")
        result = await collector.collect(datetime.now() - timedelta(days=7))
        assert result == ""

    @pytest.mark.asyncio
    async def test_cli_不可用时优雅降级(self, projects_dir):
        collector = ClaudeCodeCollector(claude_projects_dir=projects_dir)
        since = datetime.now() - timedelta(days=7)
        with patch(
            "choreo.activity.collectors.claude_code.ClaudeCodeCollector._run_cc_log",
            new=AsyncMock(return_value=""),
        ):
            result = await collector.collect(since)
        assert isinstance(result, str)  # 不抛异常

    @pytest.mark.asyncio
    async def test_项目目录不存在时返回空(self, tmp_path):
        collector = ClaudeCodeCollector(claude_projects_dir=tmp_path / "nonexistent")
        result = await collector.collect(datetime.now() - timedelta(days=7))
        assert result == ""
```

- [ ] **步骤 2：运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_activity.py -v 2>&1 | head -20
```

预期：ImportError，`claude_code.py` 尚不存在。

- [ ] **步骤 3：实现 ClaudeCodeCollector**

新建 `backend/choreo/activity/collectors/claude_code.py`：

```python
from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from choreo.activity.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

_DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"

_SENSITIVE_RE = re.compile(
    r"(api[_-]?key|token|password|secret|credential|authorization)[^\n]*",
    re.IGNORECASE,
)


def _desensitize(text: str) -> str:
    return _SENSITIVE_RE.sub(
        lambda m: m.group(0).split("=")[0].split(":")[0] + ": <redacted>",
        text,
    )


class ClaudeCodeCollector(BaseCollector):
    """通过 claude-code-log CLI + sessions-index.json 采集 Claude Code 会话行为。"""

    def __init__(self, claude_projects_dir: Path | None = None) -> None:
        self._dir = claude_projects_dir or _DEFAULT_PROJECTS_DIR

    async def collect(self, since: datetime) -> str:
        if not self._dir.exists():
            return ""

        parts: list[str] = []

        for project_dir in sorted(self._dir.iterdir()):
            if not project_dir.is_dir():
                continue

            sessions = self._recent_sessions(project_dir / "sessions-index.json", since)
            if not sessions:
                continue

            content = await self._run_cc_log(project_dir)
            total_msgs = sum(s.get("message_count", 0) for s in sessions)
            project_name = project_dir.name.replace("-", "/").strip("/")

            header = f"### 项目: {project_name}（{len(sessions)} 个会话，约 {total_msgs} 条消息）"
            body = _desensitize(content) if content.strip() else "（无详细内容）"
            parts.append(f"{header}\n\n{body}")

        if not parts:
            return ""

        start = since.strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        return f"=== Claude Code 会话（{start} ~ {end}）===\n\n" + "\n\n---\n\n".join(parts)

    def _recent_sessions(self, index_path: Path, since: datetime) -> list[dict]:
        if not index_path.exists():
            return []
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        since_ts = since.timestamp()
        result = []
        for s in data if isinstance(data, list) else []:
            raw = s.get("updated_at", 0)
            if isinstance(raw, str):
                try:
                    ts = datetime.fromisoformat(raw).timestamp()
                except ValueError:
                    continue
            else:
                ts = float(raw)
            if ts >= since_ts:
                result.append(s)
        return result

    async def _run_cc_log(self, project_dir: Path) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude-code-log",
                "--format", "md",
                "--detail", "low",
                "--compact",
                str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            return stdout.decode("utf-8", errors="replace")
        except FileNotFoundError:
            logger.warning("claude-code-log CLI 未安装，跳过内容提取")
            return ""
        except asyncio.TimeoutError:
            logger.warning("claude-code-log 超时：%s", project_dir)
            return ""
        except Exception as exc:
            logger.warning("claude-code-log 失败：%s %r", project_dir, exc)
            return ""
```

- [ ] **步骤 4：运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_activity.py -v
```

预期：全部 7 个测试 PASS。

- [ ] **步骤 5：提交**

```bash
git add backend/choreo/activity/collectors/ backend/tests/test_activity.py
git commit -m "feat(profiling): 添加 ClaudeCodeCollector（claude-code-log + sessions-index）"
```

---

## 任务 5：USER_PROFILE_PROMPT

**涉及文件：**
- 新建：`backend/choreo/kb/profile_prompt.py`

- [ ] **步骤 1：编写提示词文件**

新建 `backend/choreo/kb/profile_prompt.py`：

```python
USER_PROFILE_PROMPT = """\
# Role: 用户画像分析师

## 任务
基于本周行为数据和现有画像，增量更新用户的个人画像 wiki 页面。

## 规则
- 不删除现有画像中已有的信息；只增加、调整或提升置信度
- 新发现的偏好/技能需在数据中至少出现 2 次以上才写入画像
- 置信度低的推断需标注（如「（推测，待验证）」）
- 不捏造数据中未出现的内容
- 必须实际调用工具写出文件，不要只描述要做什么

## 执行步骤

1. 调用 kb_read("user/profile.md") 获取现有画像
   - 如果返回 "Page not found"，则从零开始创建
2. 基于【本周行为数据】更新画像内容
3. 调用 kb_write_wiki("user/profile.md", <完整更新后的 profile 内容>)
4. 调用 kb_write_wiki("user/recent-context.md", <本周上下文快照>)

## 本周行为数据（{week}，覆盖过去 {lookback_days} 天）

{collected_data}

---

## 期望输出格式

### wiki/user/profile.md（完整更新，保留所有历史信息）

```
---
title: 用户画像
type: user-profile
updated: {today}
---

## 技能与专长
（从 git 语言分布、任务类型、Claude Code 会话主题推断；标注置信度）

## 工作方式与偏好
（工具选择、沟通风格、任务拆解模式、偏好的解决路径）

## 当前关注领域
（近期反复出现的主题/项目/技术栈）

## 行为特征
（高频操作类型、决策风格、与 agent 的协作模式）
```

### wiki/user/recent-context.md（本周快照，每次覆盖）

```
---
title: 最近上下文
type: user-recent-context
week: {week}
updated: {today}
---

## 本周在做什么
（3-5 条，具体项目和任务）

## 本周关注点
（2-3 个主题/焦点）
```
"""
```

- [ ] **步骤 2：验证导入**

```bash
cd backend && uv run python -c "from choreo.kb.profile_prompt import USER_PROFILE_PROMPT; print(USER_PROFILE_PROMPT[:50])"
```

预期：打印提示词开头 50 个字符。

- [ ] **步骤 3：提交**

```bash
git add backend/choreo/kb/profile_prompt.py
git commit -m "feat(profiling): 添加 USER_PROFILE_PROMPT"
```

---

## 任务 6：profiler.py

**涉及文件：**
- 新建：`backend/choreo/activity/profiler.py`
- 修改：`backend/tests/test_activity.py`

- [ ] **步骤 1：补充 profiler 测试**

在 `backend/tests/test_activity.py` 末尾追加：

```python
class TestCollectAll:
    @pytest.mark.asyncio
    async def test_无采集器时返回空字符串(self):
        from choreo.activity.profiler import collect_all
        with patch("choreo.activity.profiler._get_collectors", return_value=[]):
            result = await collect_all(lookback_days=7)
        assert result == ""

    @pytest.mark.asyncio
    async def test_合并多个采集器输出(self):
        from choreo.activity.collectors.base import BaseCollector
        from choreo.activity.profiler import collect_all

        class 假采集器(BaseCollector):
            async def collect(self, since):
                return "采集器输出"

        with patch("choreo.activity.profiler._get_collectors", return_value=[假采集器(), 假采集器()]):
            result = await collect_all(lookback_days=7)
        assert result.count("采集器输出") == 2

    @pytest.mark.asyncio
    async def test_失败的采集器被跳过(self):
        from choreo.activity.collectors.base import BaseCollector
        from choreo.activity.profiler import collect_all

        class 坏采集器(BaseCollector):
            async def collect(self, since):
                raise RuntimeError("网络错误")

        class 好采集器(BaseCollector):
            async def collect(self, since):
                return "好的输出"

        with patch("choreo.activity.profiler._get_collectors", return_value=[坏采集器(), 好采集器()]):
            result = await collect_all(lookback_days=7)
        assert "好的输出" in result
```

- [ ] **步骤 2：运行新测试确认失败**

```bash
cd backend && uv run pytest tests/test_activity.py::TestCollectAll -v
```

预期：ImportError，`profiler.py` 尚不存在。

- [ ] **步骤 3：实现 profiler.py**

新建 `backend/choreo/activity/profiler.py`：

```python
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from choreo.activity.collectors.base import BaseCollector

logger = logging.getLogger(__name__)


def _get_collectors() -> list[BaseCollector]:
    """根据 ACTIVITY_PROFILE 配置构建采集器列表。"""
    from choreo.config import settings
    from choreo.activity.collectors.claude_code import ClaudeCodeCollector

    cfg: dict = getattr(settings, "ACTIVITY_PROFILE", {}) or {}
    sources: list[dict] = cfg.get("sources", [])

    collectors: list[BaseCollector] = []
    for src in sources:
        if src.get("type") == "claude_code_logs":
            collectors.append(ClaudeCodeCollector())

    # 未配置时默认启用 claude_code
    if not collectors:
        collectors.append(ClaudeCodeCollector())

    return collectors


async def collect_all(lookback_days: int = 7) -> str:
    """运行所有采集器并拼接输出。"""
    since = datetime.now() - timedelta(days=lookback_days)
    collectors = _get_collectors()
    parts: list[str] = []

    for collector in collectors:
        try:
            result = await collector.collect(since)
            if result.strip():
                parts.append(result)
        except Exception as exc:
            logger.warning("采集器 %s 失败: %r", type(collector).__name__, exc)

    return "\n\n---\n\n".join(parts)


async def update_profile() -> None:
    """采集行为数据，调用 KB agent 更新 wiki/user/。"""
    from choreo.config import settings
    from choreo.agents.choreo_agent import create_kb_agent
    from choreo.kb.profile_prompt import USER_PROFILE_PROMPT
    from langchain_core.messages import HumanMessage

    cfg: dict = getattr(settings, "ACTIVITY_PROFILE", {}) or {}
    lookback_days: int = int(cfg.get("lookback_days", 7))

    collected_data = await collect_all(lookback_days)
    if not collected_data.strip():
        logger.info("无行为数据，跳过画像更新")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    week = datetime.now().strftime("%Y-W%W")

    prompt = USER_PROFILE_PROMPT.format(
        week=week,
        today=today,
        lookback_days=lookback_days,
        collected_data=collected_data,
    )

    agent = create_kb_agent()
    await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
    logger.info("用户画像更新完成，周期：%s", week)


def start_profile_scheduler():
    """启动画像更新的 APScheduler，返回 scheduler 实例（关闭时调用 .shutdown()）。"""
    from choreo.config import settings
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    cfg: dict = getattr(settings, "ACTIVITY_PROFILE", {}) or {}
    if not cfg.get("enabled", False):
        logger.info("activity_profile 未启用，画像循环不启动")
        return None

    schedule: str = cfg.get("schedule", "0 9 * * 1")
    try:
        trigger = CronTrigger.from_crontab(schedule)
    except Exception as exc:
        logger.warning("activity_profile.schedule 无效 %r: %r，循环不启动", schedule, exc)
        return None

    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_profile, trigger, id="user_profile_update", replace_existing=True)
    scheduler.start()
    logger.info("用户画像调度器已启动（schedule=%s）", schedule)
    return scheduler
```

- [ ] **步骤 4：运行全部测试**

```bash
cd backend && uv run pytest tests/test_activity.py -v
```

预期：全部 10 个测试 PASS。

- [ ] **步骤 5：提交**

```bash
git add backend/choreo/activity/profiler.py backend/tests/test_activity.py
git commit -m "feat(profiling): 添加 profiler（collect_all、update_profile、调度器）"
```

---

## 任务 7：API 端点

**涉及文件：**
- 修改：`backend/choreo/gateway/routers/knowledge.py`

- [ ] **步骤 1：添加 update-profile 端点**

在 `backend/choreo/gateway/routers/knowledge.py` 中，找到 `@router.post("/lint")` 块，在其后添加：

```python
@router.post("/update-profile", status_code=202)
async def trigger_profile_update(background_tasks: BackgroundTasks):
    """手动触发用户画像更新（异步后台执行）。"""
    background_tasks.add_task(_run_profile_update)
    return {"status": "started", "message": "用户画像更新已启动，完成后写入 wiki/user/profile.md"}


async def _run_profile_update() -> None:
    try:
        from choreo.activity.profiler import update_profile
        await update_profile()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("画像更新失败: %r", exc)
```

注意：`BackgroundTasks` 应已在文件顶部导入（`/ingest` 和 `/lint` 用到了它）。如未导入，在文件顶部加 `from fastapi import BackgroundTasks`。

- [ ] **步骤 2：验证端点存在**

```bash
cd backend && uv run python -c "
from choreo.gateway.routers.knowledge import router
routes = [r.path for r in router.routes]
print(routes)
assert '/update-profile' in routes, '端点缺失'
print('ok')
"
```

预期：打印路由列表（含 `/update-profile`），然后打印 `ok`。

- [ ] **步骤 3：提交**

```bash
git add backend/choreo/gateway/routers/knowledge.py
git commit -m "feat(profiling): 添加 POST /api/kb/update-profile 端点"
```

---

## 任务 8：App Lifespan 集成

**涉及文件：**
- 修改：`backend/choreo/gateway/app.py`

- [ ] **步骤 1：在 lifespan 启动段添加调度器**

打开 `backend/choreo/gateway/app.py`，找到沙箱管理器启动块（含 `evict_task = asyncio.create_task(...)`）的位置，在其**之后**添加：

```python
    # 用户画像调度器
    from choreo.activity.profiler import start_profile_scheduler
    profile_scheduler = start_profile_scheduler()
    app.state.profile_scheduler = profile_scheduler
```

- [ ] **步骤 2：在 lifespan 清理段关闭调度器**

在 `finally:` 块中（其他关闭逻辑之前）添加：

```python
    if getattr(app.state, "profile_scheduler", None) is not None:
        app.state.profile_scheduler.shutdown(wait=False)
```

- [ ] **步骤 3：启动后端验证无报错**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload 2>&1 | head -25
```

预期：启动正常，日志显示 `activity_profile 未启用，画像循环不启动`（因配置注释掉了）。无 ImportError。

- [ ] **步骤 4：提交**

```bash
git add backend/choreo/gateway/app.py
git commit -m "feat(profiling): 在 app lifespan 中启动/关闭画像调度器"
```

---

## 任务 9：前端按钮

**涉及文件：**
- 修改：`frontend/src/pages/KnowledgePage.tsx`

- [ ] **步骤 1：找到现有的编译/Lint 按钮位置**

打开 `frontend/src/pages/KnowledgePage.tsx`，找到调用 `POST /api/kb/ingest` 和 `/api/kb/lint` 的按钮。

- [ ] **步骤 2：添加状态和处理函数**

在现有按钮的 state 和 handler 旁边添加：

```tsx
const [profilingStatus, setProfilingStatus] = useState<'idle' | 'running'>('idle');

const handleUpdateProfile = async () => {
  setProfilingStatus('running');
  try {
    await fetch('/api/kb/update-profile', { method: 'POST' });
  } finally {
    setProfilingStatus('idle');
  }
};
```

- [ ] **步骤 3：在 JSX 中添加按钮**

紧跟 Lint 按钮之后添加：

```tsx
<button
  onClick={handleUpdateProfile}
  disabled={profilingStatus === 'running'}
  className="px-3 py-1.5 text-sm rounded bg-purple-600 hover:bg-purple-700 text-white disabled:opacity-50"
>
  {profilingStatus === 'running' ? '更新中…' : '更新用户画像'}
</button>
```

- [ ] **步骤 4：在浏览器中验证**

启动前端（`cd frontend && pnpm dev`），访问知识库页面，确认按钮出现且点击不报错。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/pages/KnowledgePage.tsx
git commit -m "feat(profiling): 添加「更新用户画像」按钮"
```

---

## 任务 10：端到端验证

- [ ] **步骤 1：通过 API 手动触发**

```bash
curl -X POST http://localhost:8000/api/kb/update-profile
```

预期：`{"status":"started","message":"用户画像更新已启动..."}`

- [ ] **步骤 2：等待约 30 秒后检查产出文件**

```bash
ls -la knowledge/wiki/user/
cat knowledge/wiki/user/profile.md
```

预期：`profile.md` 和 `recent-context.md` 均存在，内容含 YAML frontmatter（`type: user-profile`）。

- [ ] **步骤 3：验证 agent 可读取画像**

```bash
cd backend && uv run python -c "
import asyncio
from choreo.agents.tools.kb_tools import kb_read
result = asyncio.run(kb_read.ainvoke({'page_path': 'user/profile.md'}))
print(result[:200])
"
```

预期：打印画像前 200 字符，而非 "Page not found"。

- [ ] **步骤 4：启用定时调度验证**

在 `backend/config.yaml` 中取消注释 `activity_profile:` 节，重启后端。

预期日志：`用户画像调度器已启动（schedule=0 9 * * 1）`

---

## 自检

**需求覆盖：**
- ✅ BaseSourceAdapter ABC — 任务 2
- ✅ BaseCollector ABC — 任务 3
- ✅ ClaudeCodeCollector（claude-code-log + sessions-index.json + 脱敏）— 任务 4
- ✅ USER_PROFILE_PROMPT（增量更新，读现有画像，写 profile + recent-context）— 任务 5
- ✅ profiler.py（collect_all、update_profile、调度器）— 任务 6
- ✅ POST /api/kb/update-profile 端点 — 任务 7
- ✅ app.py lifespan 集成 — 任务 8
- ✅ 前端按钮 — 任务 9
- ✅ 端到端验证 — 任务 10

**占位符扫描：** 无 TBD、无"待实现"，每个步骤均有完整代码。

**类型一致性：**
- `BaseCollector.collect(since: datetime) -> str` — 所有实现与测试中的假采集器一致
- `start_profile_scheduler()` 返回 `AsyncIOScheduler | None` — app.py 通过 `getattr` 安全检查
- `USER_PROFILE_PROMPT.format(week=, today=, lookback_days=, collected_data=)` — profiler.py 中四个参数均已提供
