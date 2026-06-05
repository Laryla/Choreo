# 前端框架设计文档

## 技术栈

| 技术 | 版本要求 | 用途 |
|------|----------|------|
| React | ^18 | UI 框架 |
| Vite | ^5 | 构建工具 |
| TypeScript | ^5 | 类型安全 |
| TailwindCSS | ^3 | 样式 |
| `@langchain/langgraph-sdk` | latest | 对接后端（兼容 LangGraph Server 的 FastAPI） |
| Node.js | >= 18 | 运行环境 |

> **架构说明**：前端用 `@langchain/langgraph-sdk` 的 `Client` 与后端通信。后端 FastAPI 完全对齐 LangGraph Server 的路径和 SSE 事件格式，因此 SDK 开箱可用，无需适配。

---

## 目录结构

```
frontend/
├── public/
├── src/
│   ├── pages/
│   │   ├── ChatPage.tsx          # 主页：对话 + 脚本审阅
│   │   ├── TaskListPage.tsx      # 定时任务管理
│   │   └── HistoryPage.tsx       # 运行历史与产物预览
│   ├── components/
│   │   ├── Chat/
│   │   │   ├── ChatInput.tsx     # 自然语言指令输入框
│   │   │   ├── ChatMessage.tsx   # 消息气泡（用户/Agent）
│   │   │   └── TokenStream.tsx   # LLM token 增量实时渲染
│   │   ├── ReviewPanel/
│   │   │   ├── ReviewPanel.tsx   # 脚本审阅面板（核心交互）
│   │   │   ├── ScriptViewer.tsx  # 脚本代码展示（语法高亮）
│   │   │   └── ReviewActions.tsx # 确认 / 编辑 / 拒绝操作按钮
│   │   ├── TaskList/
│   │   │   ├── TaskCard.tsx
│   │   │   └── TaskStatusBadge.tsx
│   │   └── History/
│   │       ├── HistoryList.tsx
│   │       └── OutputPreview.tsx
│   ├── lib/
│   │   └── client.ts             # LangGraph Client 单例
│   ├── hooks/
│   │   ├── useChat.ts            # 核心 hook：发消息 + 消费 SSE
│   │   └── useReview.ts          # 审阅决策提交
│   ├── api/
│   │   ├── tasks.ts              # getTasks / createTask / patchTask / deleteTask
│   │   └── history.ts            # getHistory / getOutput
│   ├── store/
│   │   ├── chatStore.ts          # 对话消息列表 & 流式 token
│   │   └── reviewStore.ts        # 待审阅状态
│   ├── types/
│   │   ├── task.ts
│   │   └── review.ts
│   ├── App.tsx
│   └── main.tsx
├── package.json
├── vite.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

---

## Client 初始化（lib/client.ts）

```typescript
import { Client } from "@langchain/langgraph-sdk";

// 指向我们的 FastAPI（实现了 LangGraph Server 兼容路径）
export const client = new Client({
  apiUrl: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
});
```

---

## 核心 Hook：useChat（hooks/useChat.ts）

使用 SDK 的 `runs.stream()` 消费 SSE 流，逻辑与对接真实 LangGraph Server 完全一样：

```typescript
import { useCallback, useState } from "react";
import { client } from "@/lib/client";
import { useChatStore } from "@/store/chatStore";
import { useReviewStore } from "@/store/reviewStore";

export function useChat() {
  const [threadId, setThreadId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const { addMessage, appendToken, finalizeToken } = useChatStore();
  const { openReview } = useReviewStore();

  // 首次发消息时创建 thread
  async function ensureThread() {
    if (threadId) return threadId;
    const thread = await client.threads.create();
    setThreadId(thread.thread_id);
    return thread.thread_id;
  }

  const sendMessage = useCallback(async (text: string) => {
    addMessage({ role: "user", content: text });
    setStreaming(true);

    const tid = await ensureThread();

    const stream = client.runs.stream(tid, "choreo", {
      input: { messages: [{ role: "user", content: text }] },
      streamMode: ["messages", "updates"],
    });

    for await (const chunk of stream) {
      if (chunk.event === "messages") {
        // LLM token 增量
        for (const msg of chunk.data) {
          if (msg.content) appendToken(msg.content);
        }
      }

      if (chunk.event === "updates") {
        // 检测人工审阅请求
        if (chunk.data.__interrupt__) {
          const payload = chunk.data.__interrupt__[0].value;
          openReview({ threadId: tid, ...payload });
          break; // SSE 挂起，等待用户决策
        }
      }
    }

    finalizeToken();
    setStreaming(false);
  }, [threadId]);

  return { sendMessage, streaming, threadId };
}
```

---

## 人工审阅 Hook：useReview（hooks/useReview.ts）

用户决策通过 `client.threads.updateState()` 提交，后端收到后唤醒挂起的 Agent，然后重新 stream 继续执行：

```typescript
import { client } from "@/lib/client";
import { useReviewStore } from "@/store/reviewStore";
import { useChatStore } from "@/store/chatStore";

export function useReview() {
  const { current, closeReview } = useReviewStore();
  const { appendToken, finalizeToken, addMessage } = useChatStore();

  async function submitDecision(
    decision: { action: "approve" | "edit" | "reject"; patch?: object; reason?: string }
  ) {
    if (!current) return;
    const { threadId, task_id } = current;

    // 将决策写入线程 state，后端 resolve_review() 唤醒 Agent
    await client.threads.updateState(threadId, {
      values: { task_id, ...decision },
    });

    closeReview();

    // 继续消费剩余的 SSE 流（Agent 从中断点恢复）
    const stream = client.runs.stream(threadId, "choreo", {
      input: null,
      streamMode: ["messages", "updates"],
    });

    for await (const chunk of stream) {
      if (chunk.event === "messages") {
        for (const msg of chunk.data) {
          if (msg.content) appendToken(msg.content);
        }
      }
    }

    finalizeToken();
  }

  return { current, submitDecision };
}
```

---

## 核心页面与组件

### ChatPage（主页面）

```
┌──────────────────────────────────────────────────────┐
│  对话区                     │  脚本审阅面板（按需显示） │
│  ─────────────────────────  │  ─────────────────────  │
│  [Agent思考流...]            │  # generate_changelog.py│
│  [你: 每周五整理changelog]   │  import subprocess ...  │
│  [Agent: 我理解了，...]      │                         │
│                             │  [确认] [编辑] [拒绝]   │
│  [输入框]          [发送]   │                         │
└──────────────────────────────────────────────────────┘
```

- 首次发消息调用 `client.threads.create()` 获取 thread_id
- 发消息走 `useChat.sendMessage()`
- 收到 `__interrupt__` 时 `ReviewPanel` 弹出

### ReviewPanel（脚本审阅面板）

| 操作 | 说明 |
|------|------|
| **确认** | `submitDecision({ action: "approve" })` |
| **编辑** | `submitDecision({ action: "edit", patch: {...} })` |
| **拒绝** | `submitDecision({ action: "reject", reason: "..." })` |

---

## 数据流

```
用户输入指令
    │
    ▼
client.threads.create()  →  获取 thread_id
    │
    ▼
client.runs.stream(threadId, "choreo", { input: {...} })
    │
    ├── event: messages    → appendToken 实时渲染
    ├── event: updates (tool_start) → 显示工具调用状态
    └── event: updates { __interrupt__: [...] }
            │
            ▼
        ReviewPanel 弹出（SSE 挂起，后端 asyncio.Event 等待）
            │
            ▼
        client.threads.updateState(threadId, { values: decision })
            │
            ▼
        后端 gate.set() → Agent 恢复执行
            │
            ▼
        client.runs.stream(threadId, "choreo", { input: null })
            │
            └── 流恢复，继续渲染结果
```

---

## 任务与历史 API（api/tasks.ts & api/history.ts）

这两类接口不走 LangGraph SDK，直接 `fetch` 调用 FastAPI 的 `/api/` 路径：

```typescript
// tasks.ts
const BASE = "/api/tasks";

export const getTasks = () => fetch(BASE).then(r => r.json());

export const createTask = (body: TaskCreate) =>
  fetch(BASE, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }).then(r => r.json());

export const patchTask = (id: string, body: { status: "active" | "paused" }) =>
  fetch(`${BASE}/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) }).then(r => r.json());

export const deleteTask = (id: string) =>
  fetch(`${BASE}/${id}`, { method: "DELETE" });

// history.ts
export const getHistory = (page = 1, size = 20, taskId?: string) => {
  const p = new URLSearchParams({ page: String(page), size: String(size) });
  if (taskId) p.set("task_id", taskId);
  return fetch(`/api/history?${p}`).then(r => r.json());
};

export const getOutput = (runId: string) =>
  fetch(`/api/history/${runId}/output`).then(r => r.text());
```

---

## 环境变量

```ini
VITE_API_URL=http://localhost:8000
```

---

## 开发启动

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173
```

`vite.config.ts` 代理所有请求到后端：

```typescript
export default defineConfig({
  server: {
    proxy: {
      "/threads": { target: "http://localhost:8000" },
      "/api":     { target: "http://localhost:8000" },
    },
  },
})
```
