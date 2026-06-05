# Context Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入 LangChain 内置的 `SummarizationMiddleware`，在单个对话线程 token 用量达到阈值时自动压缩历史消息，保持模型注意力集中。

**Architecture:** `SummarizationMiddleware` 挂在 `before_model` 钩子，每次 LLM 调用前检查 token 用量，超过阈值时用 LLM 把旧消息压缩成结构化摘要（SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS），替换进 state，保留最近 N 条消息原文。交互式 agent 和无人值守 headless agent 各自启用，参数通过 `config.py` 配置。

**Tech Stack:** `langchain.agents.middleware.summarization.SummarizationMiddleware`（已内置，无需安装新依赖）

---

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 修改 | `backend/choreo/config.py` |
| 修改 | `backend/choreo/agents/middlewares/__init__.py` |
| 修改 | `backend/choreo/agents/choreo_agent.py` |
| 创建 | `backend/tests/test_context_compression.py` |

---

## Task 1: 添加配置项

**Files:**
- Modify: `backend/choreo/config.py`

- [ ] **Step 1: 在 `Settings` 类末尾添加压缩相关配置**

在 `backend/choreo/config.py` 的 `FEISHU_ENABLED` 行之后，`settings = Settings()` 之前，添加：

```python
    # 上下文压缩
    CONTEXT_COMPRESSION_ENABLED: bool = True
    # 触发阈值：消息条数（任一满足即触发）
    CONTEXT_COMPRESSION_TRIGGER_MESSAGES: int = 60
    # 触发阈值：token 数量
    CONTEXT_COMPRESSION_TRIGGER_TOKENS: int = 60000
    # 压缩后保留的最近消息条数
    CONTEXT_COMPRESSION_KEEP_MESSAGES: int = 20
```

- [ ] **Step 2: 验证配置可读**

```bash
cd backend && python3 -c "from choreo.config import settings; print(settings.CONTEXT_COMPRESSION_ENABLED, settings.CONTEXT_COMPRESSION_TRIGGER_MESSAGES)"
```

Expected: `True 60`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/config.py
git commit -m "feat(config): add context compression settings"
```

---

## Task 2: 写测试（先写失败的）

**Files:**
- Create: `backend/tests/test_context_compression.py`

- [ ] **Step 1: 创建测试文件**

```python
"""Tests for context compression middleware integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents.middleware.summarization import SummarizationMiddleware


def test_summarization_middleware_instantiation():
    """SummarizationMiddleware can be created with our config values."""
    from choreo.config import settings
    from choreo.model_factory import load_model

    llm = load_model()
    middleware = SummarizationMiddleware(
        model=llm,
        trigger=[
            ("messages", settings.CONTEXT_COMPRESSION_TRIGGER_MESSAGES),
            ("tokens", settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS),
        ],
        keep=("messages", settings.CONTEXT_COMPRESSION_KEEP_MESSAGES),
    )
    assert middleware is not None
    assert middleware.keep == ("messages", settings.CONTEXT_COMPRESSION_KEEP_MESSAGES)


def test_no_summarize_under_threshold():
    """Middleware does not summarize when message count is below threshold."""
    from choreo.config import settings
    from choreo.model_factory import load_model

    llm = load_model()
    middleware = SummarizationMiddleware(
        model=llm,
        trigger=[("messages", 10)],
        keep=("messages", 5),
    )
    state = {"messages": [HumanMessage(content="hello"), AIMessage(content="hi")]}
    runtime = MagicMock()
    result = middleware.before_model(state, runtime)
    assert result is None


def test_summarize_triggered_by_message_count():
    """Middleware triggers when message count exceeds threshold."""
    from choreo.model_factory import load_model

    llm = load_model()
    middleware = SummarizationMiddleware(
        model=llm,
        trigger=[("messages", 3)],
        keep=("messages", 2),
    )
    messages = [
        HumanMessage(content=f"message {i}", id=f"msg-{i}") for i in range(5)
    ]
    state = {"messages": messages}
    runtime = MagicMock()

    with patch.object(middleware, "_create_summary", return_value="摘要内容"):
        result = middleware.before_model(state, runtime)

    assert result is not None
    assert "messages" in result
```

- [ ] **Step 2: 运行测试，确认可以跑通（instantiation test 应当通过，其他两个也应通过）**

```bash
cd backend && uv run pytest tests/test_context_compression.py -v
```

Expected: 3 passed（如果 load_model 需要环境变量，用 `.env` 里的配置运行）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_context_compression.py
git commit -m "test(compression): add context compression middleware tests"
```

---

## Task 3: 接入 choreo_agent.py

**Files:**
- Modify: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: 在文件顶部添加 import**

在 `choreo_agent.py` 的现有 import 块末尾（`from choreo.config import settings` 之后）添加：

```python
from langchain.agents.middleware.summarization import SummarizationMiddleware
```

- [ ] **Step 2: 添加工厂函数**

在 `llm = load_model()` 之后，`create_choreo_agent` 函数定义之前，添加：

```python
def _make_compression_middleware() -> SummarizationMiddleware | None:
    if not settings.CONTEXT_COMPRESSION_ENABLED:
        return None
    return SummarizationMiddleware(
        model=llm,
        trigger=[
            ("messages", settings.CONTEXT_COMPRESSION_TRIGGER_MESSAGES),
            ("tokens", settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS),
        ],
        keep=("messages", settings.CONTEXT_COMPRESSION_KEEP_MESSAGES),
    )
```

- [ ] **Step 3: 在 headless agent 的 middleware 列表中加入压缩中间件**

找到 headless 分支的：
```python
        middleware = [
            ModelSelectorMiddleware(),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
        ]
```

替换为：
```python
        _compression = _make_compression_middleware()
        middleware = [
            *([_compression] if _compression else []),
            ModelSelectorMiddleware(),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
        ]
```

- [ ] **Step 4: 在交互式 agent 的 middleware 列表中加入压缩中间件**

找到 interactive agent 的：
```python
        middleware=[
            McpContextMiddleware(),
            SkillsContextMiddleware(),
            ModelSelectorMiddleware(),
            UnifiedHITLMiddleware(
```

替换为：
```python
        middleware=[
            *([_make_compression_middleware()] if settings.CONTEXT_COMPRESSION_ENABLED else []),
            McpContextMiddleware(),
            SkillsContextMiddleware(),
            ModelSelectorMiddleware(),
            UnifiedHITLMiddleware(
```

- [ ] **Step 5: 验证导入正常**

```bash
cd backend && python3 -c "from choreo.agents.choreo_agent import create_choreo_agent; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/agents/choreo_agent.py
git commit -m "feat(agent): integrate SummarizationMiddleware for context compression"
```

---

## Task 4: 更新 __init__.py 导出（可选）

**Files:**
- Modify: `backend/choreo/agents/middlewares/__init__.py`

> 注意：`SummarizationMiddleware` 来自 langchain 库本身，不需要创建新文件，也不需要加到 `__init__.py`。这个 task 只在你希望统一从 `choreo.agents.middlewares` 导出时才需要。可跳过。

---

## Task 5: 运行全部测试验证

- [ ] **Step 1: 运行测试**

```bash
cd backend && uv run pytest tests/test_context_compression.py -v
```

Expected: 3 passed

- [ ] **Step 2: 启动后端，验证服务正常**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload
```

Expected: 启动成功，无 import error

- [ ] **Step 3: Final commit**

```bash
git add -u
git commit -m "feat: enable context compression via SummarizationMiddleware"
```

---

## 压缩机制总结（实现细节）

| 项目 | 配置 |
|------|------|
| 触发条件 | 消息条数 ≥ 60 **或** token 数 ≥ 60,000（任一满足） |
| 保留原文 | 最近 20 条消息不压缩 |
| 压缩内容 | 第 1 条到第 N-20 条，AI/Tool pair 不拆分 |
| 摘要结构 | SESSION INTENT / SUMMARY / ARTIFACTS / NEXT STEPS |
| 摘要位置 | 插入为 HumanMessage，放在保留消息之前 |
| 压缩模型 | 与 agent 使用相同的 LLM（`llm = load_model()`） |
| 位置 | middleware 列表最前（在 HITL、ModelSelector 之前先压缩） |
