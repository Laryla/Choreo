# Sub-Agent Real-Time Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 子代理执行时，每一步工具调用实时透传到前端 SSE 流，前端展示可展开的 TaskCard。

**Architecture:** 在 `task` 工具内调用 `get_stream_writer()` 获取父流写入器，`SubagentExecutor` 改用 `astream_events()` 迭代子代理事件，每步通过写入器注入 `custom` 事件；`runs.py` 已经转发所有 `custom` 事件无需修改；前端 `useChat.ts` 解析新的 `subagent_event` 结构并按 `task_id` 归组，`ChatMessage.tsx` 新增 `TaskCard` 组件实时渲染子步骤。

**Tech Stack:** LangGraph `get_stream_writer()` + `astream_events(version="v2")` · FastAPI SSE · React + TypeScript · Zustand-like context store

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/choreo/agents/sub_agents/executor.py` | Modify | `aexecute()` 改用 `astream_events`，接收 `stream_writer` + `task_id` |
| `backend/choreo/agents/tools/task_tool.py` | Modify | 调用 `get_stream_writer()`，生成 `task_id`，传给 executor |
| `backend/choreo/gateway/routers/runs.py` | **不改** | 已转发所有 `custom` 事件 |
| `frontend/src/store/chatStore.tsx` | Modify | 新增 `SubAgentStep` 类型，Message 加 `task_steps` 字段，加 `upsertTaskStep` action |
| `frontend/src/hooks/useChat.ts` | Modify | 解析 `custom` 事件中的 `subagent_event`，按 task_id 更新 message |
| `frontend/src/components/Chat/ChatMessage.tsx` | Modify | 新增 `TaskCard` 组件，替换 `task` 工具的渲染逻辑 |

---

## Task 1: Backend — SubagentExecutor 支持流式透传

**Files:**
- Modify: `backend/choreo/agents/sub_agents/executor.py`

### 背景
`aexecute()` 目前用 `ainvoke()`，子代理运行是黑盒。改用 `astream_events(version="v2")` 后，每个工具调用开始/结束事件都会暴露出来，通过 `stream_writer` 推送给父流。

- [ ] **Step 1: 写测试（验证 stream_writer 被调用）**

创建 `backend/tests/test_subagent_streaming.py`：

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_aexecute_calls_stream_writer():
    """stream_writer 应在子代理每次工具调用时被调用至少一次。"""
    from choreo.agents.sub_agents.executor import SubagentExecutor
    from choreo.agents.sub_agents.config import SubagentConfig

    config = SubagentConfig(
        name="test",
        description="test",
        system_prompt="you are a test agent",
        tools=None,
        disallowed_tools=[],
    )

    written_events = []
    stream_writer = lambda event: written_events.append(event)

    # Mock create_agent to return a fake agent whose astream_events yields one tool call
    fake_event = {
        "event": "on_tool_start",
        "name": "bash",
        "run_id": "abc",
        "data": {"input": {"command": "echo hi"}},
    }

    async def fake_astream_events(*args, **kwargs):
        yield fake_event
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "run_id": "root",
            "data": {"output": {"messages": [MagicMock(content="done", tool_calls=[])]}},
        }

    mock_agent = MagicMock()
    mock_agent.astream_events = fake_astream_events

    with patch("langchain.agents.create_agent", return_value=mock_agent), \
         patch("choreo.model_factory.load_model", return_value=MagicMock()):
        executor = SubagentExecutor(config=config, all_tools=[], parent_model_name=None)
        result = await executor.aexecute(
            task="run echo hi",
            thread_id="t1",
            task_id="tid1",
            stream_writer=stream_writer,
        )

    assert any("subagent_event" in e for e in written_events), \
        f"Expected subagent_event in written events, got: {written_events}"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_subagent_streaming.py -v 2>&1 | tail -20
```

期望：`FAILED` with `TypeError: aexecute() got an unexpected keyword argument 'task_id'`

- [ ] **Step 3: 实现新版 `aexecute()`**

完整替换 `backend/choreo/agents/sub_agents/executor.py`：

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Any

from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from choreo.agents.sub_agents.config import SubagentConfig

logger = logging.getLogger(__name__)


def _filter_tools(
    all_tools: list[BaseTool],
    allowlist: list[str] | None,
    denylist: list[str],
) -> list[BaseTool]:
    if allowlist is not None:
        tools = [t for t in all_tools if t.name in allowlist]
    else:
        tools = list(all_tools)
    deny_set = set(denylist)
    return [t for t in tools if t.name not in deny_set]


class SubagentExecutor:
    def __init__(
        self,
        config: SubagentConfig,
        all_tools: list[BaseTool],
        parent_model_name: str | None = None,
    ) -> None:
        self.config = config
        self.tools = _filter_tools(all_tools, config.tools, config.disallowed_tools)
        self.model_name = parent_model_name if config.model == "inherit" else config.model
        logger.debug(
            "SubagentExecutor[%s]: %d tools available, model=%s",
            config.name, len(self.tools), self.model_name,
        )

    async def aexecute(
        self,
        task: str,
        thread_id: str,
        task_id: str | None = None,
        stream_writer: Callable[[Any], None] | None = None,
    ) -> str:
        from langchain.agents import create_agent
        from choreo.model_factory import load_model

        agent = create_agent(
            model=load_model(self.model_name),
            tools=self.tools,
            system_prompt=self.config.system_prompt,
        )
        sub_thread_id = f"{self.config.name}-{thread_id}"
        logger.info("Sub-agent[%s] starting, thread=%s", self.config.name, sub_thread_id)

        final_messages = []

        async for event in agent.astream_events(
            {"messages": [{"role": "user", "content": task}]},
            config={"configurable": {"thread_id": sub_thread_id}},
            version="v2",
        ):
            event_type = event.get("event", "")

            # 透传工具调用开始事件
            if event_type == "on_tool_start" and stream_writer and task_id:
                stream_writer({
                    "subagent_event": {
                        "task_id": task_id,
                        "subagent_type": self.config.name,
                        "event_type": "tool_call",
                        "tool_name": event.get("name", ""),
                        "tool_args": event.get("data", {}).get("input", {}),
                    }
                })

            # 透传工具调用结果事件
            elif event_type == "on_tool_end" and stream_writer and task_id:
                output = event.get("data", {}).get("output", "")
                stream_writer({
                    "subagent_event": {
                        "task_id": task_id,
                        "subagent_type": self.config.name,
                        "event_type": "tool_result",
                        "tool_name": event.get("name", ""),
                        "content": str(output)[:500],  # 截断避免过大
                    }
                })

            # 收集最终消息
            elif event_type == "on_chain_end" and event.get("name") == "LangGraph":
                output = event.get("data", {}).get("output", {})
                final_messages = output.get("messages", [])

        # 通知子代理完成
        if stream_writer and task_id:
            stream_writer({
                "subagent_event": {
                    "task_id": task_id,
                    "subagent_type": self.config.name,
                    "event_type": "done",
                }
            })

        # 提取最终文本结果
        for msg in reversed(final_messages):
            content = getattr(msg, "content", None)
            if content and not getattr(msg, "tool_calls", None):
                if isinstance(content, str) and content.strip():
                    return content
                if isinstance(content, list):
                    text = " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                    if text.strip():
                        return text.strip()

        return "子代理完成但未返回文本结果。"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_subagent_streaming.py -v 2>&1 | tail -10
```

期望：`PASSED`

- [ ] **Step 5: 提交**

```bash
git add backend/choreo/agents/sub_agents/executor.py backend/tests/test_subagent_streaming.py
git commit -m "feat(subagent): stream tool events via get_stream_writer"
```

---

## Task 2: Backend — task_tool 注入 stream_writer 和 task_id

**Files:**
- Modify: `backend/choreo/agents/tools/task_tool.py`

### 背景
`get_stream_writer()` 只能在 LangGraph 节点执行上下文中调用（`task` 工具 IS 在 tools 节点里执行，所以可以调用）。每次 `task` 调用生成唯一 `task_id`，透传给 executor。

- [ ] **Step 1: 修改 task_tool.py**

完整替换 `backend/choreo/agents/tools/task_tool.py`：

```python
"""
task tool — dispatches a sub-task to a specialized sub-agent.

The main Choreo agent calls task(subagent_type, description, prompt) to delegate
work to a focused sub-agent (research, coder, executor). Each sub-agent has its own
tool set and system prompt; it cannot call task() recursively (disallowed_tools).
"""
from __future__ import annotations

import logging
import uuid

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _get_all_tools() -> list:
    """Build the full tool list without importing from choreo_agent (avoids circular import)."""
    from choreo.agents.tools import (
        read_git_log, send_notification,
        read_file, write_file, edit_file, list_dir, grep, bash, skill_view,
    )
    from choreo.agents.tools.skill_tool import skill_patch, skill_create
    from choreo.agents.tools.mcp_tool import mcp_call, mcp_describe
    from choreo.agents.tools.web_tools import web_search, fetch_url

    return [
        read_git_log, send_notification,
        read_file, write_file, edit_file, list_dir, grep, bash, skill_view,
        skill_patch, skill_create,
        mcp_call, mcp_describe,
        web_search, fetch_url,
    ]


@tool
async def task(subagent_type: str, description: str, prompt: str) -> str:
    """
    把一个子任务分配给专门的子代理执行。

    Args:
        subagent_type: 子代理类型。可选值:
            - research：联网搜索、抓取网页（查 GitHub/文档/新闻等）
            - coder：读写文件、代码分析和修改
            - executor：执行 bash 命令
        description: 一句话说明这个任务做什么（用于日志）
        prompt: 给子代理的完整任务描述，越详细越好
    """
    from choreo.agents.sub_agents.registry import get_subagent_config, list_subagents
    from choreo.agents.sub_agents.executor import SubagentExecutor
    from langgraph.config import get_config, get_stream_writer

    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(list_subagents())
        return f"未知子代理类型: {subagent_type!r}。可用类型: {available}"

    parent_config = get_config()
    thread_id = (parent_config.get("configurable") or {}).get("thread_id", "unknown")
    model_name = (parent_config.get("configurable") or {}).get("model_name")

    task_id = str(uuid.uuid4())[:8]
    logger.info(
        "task tool: dispatching to sub-agent[%s], thread=%s, task_id=%s",
        subagent_type, thread_id, task_id,
    )

    # get_stream_writer() 在 LangGraph tools 节点上下文中可用，返回父流写入器
    try:
        stream_writer = get_stream_writer()
    except Exception:
        stream_writer = None

    # 通知前端子代理开始
    if stream_writer:
        stream_writer({
            "subagent_event": {
                "task_id": task_id,
                "subagent_type": subagent_type,
                "event_type": "start",
                "description": description,
            }
        })

    executor = SubagentExecutor(
        config=config,
        all_tools=_get_all_tools(),
        parent_model_name=model_name,
    )
    return await executor.aexecute(
        prompt,
        thread_id=thread_id,
        task_id=task_id,
        stream_writer=stream_writer,
    )
```

- [ ] **Step 2: 验证导入没有循环**

```bash
cd backend && uv run python -c "from choreo.agents.tools.task_tool import task; print('OK')" 2>&1 | grep -v warning | grep -v VIRTUAL
```

期望输出：`OK`

- [ ] **Step 3: 提交**

```bash
git add backend/choreo/agents/tools/task_tool.py
git commit -m "feat(task-tool): inject stream_writer and task_id for real-time streaming"
```

---

## Task 3: Frontend — chatStore 新增 SubAgentStep 类型

**Files:**
- Modify: `frontend/src/store/chatStore.tsx`

### 背景
Message 需要一个 `taskSteps` 字段存放子代理的执行步骤，并且需要一个 `upsertTaskStep` action 来实时追加/更新步骤。

- [ ] **Step 1: 读取现有 chatStore**

读取 `frontend/src/store/chatStore.tsx` 确认当前类型定义（Message, ToolCall 等）。

- [ ] **Step 2: 修改 chatStore.tsx**

在现有 `ToolCall` 接口之后添加新类型，在 `Message` 接口添加 `taskSteps` 字段，在 store 中添加 `upsertTaskStep` action。

新增类型（加在 `ToolCall` 接口后）：

```typescript
export interface SubAgentStep {
  tool_name?: string
  tool_args?: Record<string, unknown>
  content?: string          // tool result preview
  event_type: "start" | "tool_call" | "tool_result" | "done"
}

export interface TaskSteps {
  task_id: string
  subagent_type: string
  description?: string
  status: "running" | "done"
  steps: SubAgentStep[]
}
```

在 `Message` 接口中添加字段：

```typescript
taskSteps?: Record<string, TaskSteps>   // task_id → TaskSteps
```

在 `ChatState` 接口中添加 action：

```typescript
upsertTaskStep: (messageId: string, taskId: string, update: Partial<TaskSteps> & { step?: SubAgentStep }) => void
```

在 `ChatProvider` 中实现 `upsertTaskStep`：

```typescript
const upsertTaskStep = useCallback(
  (messageId: string, taskId: string, update: Partial<TaskSteps> & { step?: SubAgentStep }) => {
    setMessages(prev =>
      prev.map(msg => {
        if (msg.id !== messageId) return msg
        const existing = msg.taskSteps?.[taskId]
        const { step, ...rest } = update
        const updated: TaskSteps = {
          task_id: taskId,
          subagent_type: existing?.subagent_type ?? rest.subagent_type ?? "",
          description: rest.description ?? existing?.description,
          status: rest.status ?? existing?.status ?? "running",
          steps: step ? [...(existing?.steps ?? []), step] : (existing?.steps ?? []),
        }
        return {
          ...msg,
          taskSteps: { ...(msg.taskSteps ?? {}), [taskId]: updated },
        }
      })
    )
  },
  []
)
```

加入 context value：
```typescript
value={{ ..., upsertTaskStep }}
```

- [ ] **Step 3: 验证 TypeScript 编译**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -20
```

期望：无类型错误（或只有 pre-existing 错误）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/store/chatStore.tsx
git commit -m "feat(store): add SubAgentStep types and upsertTaskStep action"
```

---

## Task 4: Frontend — useChat.ts 解析 subagent_event

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`

### 背景
`runs.py` 已经把 `custom` 事件转发出来，格式为 `event: custom\ndata: {"subagent_event": {...}}\n\n`。`useChat.ts` 需要识别 `subagent_event` 类型，找到当前流式消息 ID，调用 `upsertTaskStep`。

- [ ] **Step 1: 读取当前 useChat.ts**

读取 `frontend/src/hooks/useChat.ts` 确认 `custom` 事件的当前处理位置（大约 137-142 行）。

- [ ] **Step 2: 修改 custom 事件处理**

找到处理 `custom` 的代码块，在解析 `custom` 数据中加入对 `subagent_event` 的处理：

```typescript
// 在 useChat.ts 里，找到处理 "custom" chunk 的代码段，替换为：
if (chunkType === "custom") {
  const d = chunk.data as Record<string, unknown>
  
  // 子代理实时步骤事件
  if (d?.subagent_event) {
    const evt = d.subagent_event as {
      task_id: string
      subagent_type: string
      event_type: "start" | "tool_call" | "tool_result" | "done"
      description?: string
      tool_name?: string
      tool_args?: Record<string, unknown>
      content?: string
    }
    // 找到当前正在流式的 assistant 消息 ID
    // streamingMsgIdRef 追踪当前消息（见下方）
    const msgId = streamingMsgIdRef.current
    if (msgId) {
      if (evt.event_type === "start") {
        upsertTaskStep(msgId, evt.task_id, {
          subagent_type: evt.subagent_type,
          description: evt.description,
          status: "running",
        })
      } else if (evt.event_type === "tool_call") {
        upsertTaskStep(msgId, evt.task_id, {
          step: {
            event_type: "tool_call",
            tool_name: evt.tool_name,
            tool_args: evt.tool_args,
          },
        })
      } else if (evt.event_type === "tool_result") {
        upsertTaskStep(msgId, evt.task_id, {
          step: {
            event_type: "tool_result",
            tool_name: evt.tool_name,
            content: evt.content,
          },
        })
      } else if (evt.event_type === "done") {
        upsertTaskStep(msgId, evt.task_id, { status: "done" })
      }
    }
    return
  }

  // 原有 custom 事件（进度状态）
  addMessage({ role: "system", content: `⚙️ ${JSON.stringify(d)}` })
}
```

`streamingMsgIdRef` 需要在 `useChat` 里新增：

```typescript
// 在 useChat 顶部 ref 区域添加
const streamingMsgIdRef = useRef<string | null>(null)

// 在 finalizeToken() 调用前（或 appendToken 第一次调用时）设置 ref：
// 在 chatStore 的 finalizeToken 返回新 message id，或在 addMessage 时记录
// 简单方案：在 "updates" 事件创建 assistant message 后记录其 id
```

**注意**：如果 `chatStore` 的 `addMessage` 不返回 id，需要同时在 chatStore 的 `addMessage` 里返回新 message 的 id，或者在 `updates` 里用 `finalizeToken` 拿到当前流式消息 id。具体实现取决于当前 chatStore 实现。

从 context 里解构 `upsertTaskStep`：

```typescript
const { addMessage, appendToken, appendThinking, finalizeToken, resetMessages, upsertTaskStep } = useChatStore()
```

- [ ] **Step 3: 追踪 streamingMsgId**

在 chatStore 的 `finalizeToken` 实现里，让它返回创建的 message id；或者更简单：在 `appendToken` 第一次调用时，在 chatStore 里记录当前流式 message id 并通过新的 getter 暴露给 useChat。

最简方案 — 在 chatStore 添加：
```typescript
streamingMsgId: string | null   // 当前流式消息的 id（finalizeToken 后变 null）
```

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 5: 提交**

```bash
git add frontend/src/hooks/useChat.ts frontend/src/store/chatStore.tsx
git commit -m "feat(useChat): parse subagent_event from custom SSE stream"
```

---

## Task 5: Frontend — TaskCard 组件

**Files:**
- Modify: `frontend/src/components/Chat/ChatMessage.tsx`

### 背景
当 `tool_calls` 中有 `name === "task"` 的调用时，用 `TaskCard` 替换原有 `ToolCallCard`。`TaskCard` 读取 `message.taskSteps[task_id]`，实时展示子代理执行步骤。

**关键**：`task_id` 在 `subagent_event.start` 事件里携带，但 `ToolCall.args.task_id` 目前不存在。需要通过 `description` 或按顺序匹配 `taskSteps`。最简方案：`taskSteps` 里只会有一个 running 的 task，按 `tool_call.id` 顺序匹配 `taskSteps` 数组顺序。

- [ ] **Step 1: 新增 TaskCard 组件**

在 `ChatMessage.tsx` 中，找到 `ToolCallCard` 组件定义之后，添加新的 `TaskCard` 组件：

```tsx
interface TaskCardProps {
  toolCall: ToolCall
  taskSteps?: Record<string, TaskSteps>  // from message.taskSteps
  taskIndex: number  // index among task tool calls (for matching)
}

function TaskCard({ toolCall, taskSteps, taskIndex }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false)
  
  // 按 index 匹配 taskSteps（按 start 事件顺序）
  const allTaskSteps = Object.values(taskSteps ?? {})
  const ts = allTaskSteps[taskIndex]
  
  const subagentType = (toolCall.args?.subagent_type as string) ?? ts?.subagent_type ?? "?"
  const description = (toolCall.args?.description as string) ?? ts?.description ?? ""
  const isRunning = !ts || ts.status === "running"
  const stepCount = ts?.steps?.length ?? 0

  const typeColors: Record<string, { badge: string; text: string; dot: string }> = {
    research: { badge: "bg-violet-900/60 text-violet-300 border border-violet-700/40", text: "text-violet-400", dot: "bg-violet-400" },
    coder:    { badge: "bg-emerald-900/60 text-emerald-300 border border-emerald-700/40", text: "text-emerald-400", dot: "bg-emerald-400" },
    executor: { badge: "bg-rose-900/60 text-rose-300 border border-rose-700/40", text: "text-rose-400", dot: "bg-rose-400" },
  }
  const colors = typeColors[subagentType] ?? typeColors.research

  return (
    <div className="rounded-lg border border-violet-900/50 bg-[#0e0a1e] my-2 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer bg-[#130d28] hover:bg-[#1a1235]"
        onClick={() => setExpanded(e => !e)}
      >
        <span className={`text-[11px] font-bold px-2 py-0.5 rounded ${colors.badge}`}>
          子代理
        </span>
        <span className={`text-xs font-semibold ${colors.text}`}>{subagentType}</span>
        <span className="flex-1 text-sm text-violet-200/80 truncate">{description}</span>
        {isRunning ? (
          <span className="flex items-center gap-1.5 text-amber-400 text-xs">
            <span className="inline-block w-3 h-3 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
            运行中
          </span>
        ) : (
          <>
            <span className="text-emerald-400 text-xs">✓ 完成</span>
            <span className="text-gray-500 text-[11px]">{stepCount} 步</span>
          </>
        )}
        <span className={`text-[10px] text-gray-500 transition-transform ${expanded ? "rotate-180" : ""}`}>▼</span>
      </div>

      {/* Body */}
      {expanded && (
        <div className="border-t border-violet-900/50 bg-[#0a0718]">
          <div className="p-2 space-y-1">
            {(ts?.steps ?? []).map((step, i) => (
              <div key={i} className="flex items-start gap-2 text-xs px-2 py-1">
                <span className={`mt-1 w-1.5 h-1.5 rounded-full flex-shrink-0 ${colors.dot}`} />
                {step.event_type === "tool_call" ? (
                  <span className="text-gray-300">
                    <span className="text-gray-400 font-mono">{step.tool_name}</span>
                    {step.tool_args && (
                      <span className="text-gray-500 ml-2">
                        {Object.entries(step.tool_args).slice(0, 1).map(([k, v]) => `${String(v).slice(0, 60)}`).join("")}
                      </span>
                    )}
                  </span>
                ) : step.event_type === "tool_result" ? (
                  <span className="text-gray-500 font-mono">
                    ↳ {step.content?.slice(0, 80)}
                  </span>
                ) : null}
              </div>
            ))}
            {isRunning && (
              <div className="flex items-center gap-2 px-2 py-1 text-xs text-gray-500">
                <span className="inline-block w-2.5 h-2.5 border border-gray-600 border-t-gray-400 rounded-full animate-spin" />
                执行中…
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 在消息渲染逻辑中使用 TaskCard**

在 `ChatMessage.tsx` 的主消息渲染逻辑里，找到遍历 `tool_calls` 的部分，将 `task` 类型的工具调用替换为 `TaskCard`：

```tsx
// 找到渲染 tool_calls 的地方，大致如下：
// {msg.tool_calls?.map(tc => <ToolCallCard key={tc.id} toolCall={tc} />)}
// 替换为：

{(() => {
  let taskIndex = 0
  return msg.tool_calls?.map(tc => {
    if (tc.name === "task") {
      const card = (
        <TaskCard
          key={tc.id}
          toolCall={tc}
          taskSteps={msg.taskSteps}
          taskIndex={taskIndex}
        />
      )
      taskIndex++
      return card
    }
    return <ToolCallCard key={tc.id} toolCall={tc} />
  })
})()}
```

并确保 `Message` 类型的 `taskSteps` 已从 props 传入（ChatMessage 接收完整 `Message` 对象）。

- [ ] **Step 3: 确保导入**

在 `ChatMessage.tsx` 顶部，确保导入了：

```tsx
import { useState } from "react"
import type { Message, ToolCall, TaskSteps } from "../../store/chatStore"
```

（根据实际导入路径调整）

- [ ] **Step 4: 验证 TypeScript 编译**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -20
```

期望：无新增类型错误

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/Chat/ChatMessage.tsx
git commit -m "feat(ui): add TaskCard component for real-time sub-agent step display"
```

---

## Task 6: 端到端验证

- [ ] **Step 1: 启动后端**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload
```

- [ ] **Step 2: 启动前端**

```bash
cd frontend && pnpm dev
```

- [ ] **Step 3: 触发子代理**

在 chat 里发送：`帮我搜索 LangGraph 0.3 的 multi-agent 文档`

期望行为：
1. 主 agent 调用 `task(subagent_type="research", ...)`
2. chat 里出现 TaskCard，显示 `⏳ 运行中`
3. TaskCard 可展开，展开后步骤实时追加（web_search、fetch_url）
4. 子代理完成后 TaskCard 显示 `✓ 完成 N步`
5. 主 agent 继续生成最终文本回复

- [ ] **Step 4: 确认无控制台错误**

打开浏览器开发者工具，确认无 TypeScript/runtime 错误。

---

## 已知边界情况

| 情况 | 处理方式 |
|------|---------|
| `get_stream_writer()` 在非 LangGraph 上下文调用 | try/except，`stream_writer=None`，退化为不透传 |
| 子代理 `astream_events` 失败 | executor 捕获异常，返回错误字符串 |
| `taskIndex` 和 `taskSteps` 顺序不对 | Phase 2 可改为在 `task` tool args 里直接带 `task_id`，前端精确匹配 |
| tool_result 内容过大 | executor 截断到 500 chars |
