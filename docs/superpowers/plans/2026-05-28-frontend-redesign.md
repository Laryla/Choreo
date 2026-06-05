# Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Choreo 前端从顶部 Tab 布局重构为 Claude 风格侧边栏，支持 Tailwind CSS dark mode 双主题切换。

**Architecture:** 启用 Tailwind `darkMode: 'class'`，在 `<html>` 上切换 `dark` class 实现主题。用 `react-router-dom` 替换 `useState` 路由，侧边栏固定 230px，内容区居中 max-w-[740px]。

**Tech Stack:** React 18, TypeScript, Tailwind CSS 3, react-router-dom v6, @langchain/langgraph-sdk

---

## 文件变更地图

| 操作 | 路径 | 职责 |
|---|---|---|
| 修改 | `tailwind.config.ts` | 开启 `darkMode: 'class'` |
| 修改 | `src/index.css` | 全局基础样式（body 背景等） |
| 新建 | `src/hooks/useTheme.ts` | 主题切换 + localStorage 持久化 |
| 新建 | `src/components/Sidebar/Sidebar.tsx` | 侧边栏组件 |
| 新建 | `src/components/Topbar/Topbar.tsx` | 顶栏组件 |
| 修改 | `src/App.tsx` | 引入 react-router，渲染 Sidebar + Outlet |
| 修改 | `src/pages/ChatPage.tsx` | 适配新布局，移除旧 Provider 包裹 |
| 修改 | `src/components/Chat/ChatMessage.tsx` | AI 消息无气泡，user 消息深色 |
| 修改 | `src/components/Chat/ChatInput.tsx` | 新样式，max-w-[740px] |
| 修改 | `src/components/ReviewPanel/ReviewPanel.tsx` | 改为内嵌卡片（非侧边栏面板） |
| 修改 | `src/pages/TaskListPage.tsx` | 适配新布局样式 |
| 修改 | `src/pages/HistoryPage.tsx` | 空状态占位 |
| 修改 | `src/hooks/useChat.ts` | 无变化（保持不动） |
| 修改 | `src/hooks/useReview.ts` | 无变化（保持不动） |

---

## Task 1：开启 Tailwind dark mode + 安装 react-router-dom

**Files:**
- Modify: `tailwind.config.ts`
- Modify: `src/index.css`
- Run: `pnpm add react-router-dom`

- [ ] **Step 1: 安装 react-router-dom**

```bash
cd frontend && pnpm add react-router-dom @types/react-router-dom
```

- [ ] **Step 2: 开启 Tailwind class-based dark mode**

`tailwind.config.ts` 完整内容：
```ts
import type { Config } from "tailwindcss";
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: { extend: {} },
  plugins: [],
} satisfies Config;
```

- [ ] **Step 3: 设置 index.css 全局背景**

`src/index.css` 完整内容：
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
}

body {
  @apply bg-[#f5f2eb] dark:bg-[#141414];
}
```

- [ ] **Step 4: 验证 Tailwind 编译正常**

```bash
cd frontend && pnpm dev
```

打开浏览器，确认页面无报错即可（样式此时会乱，正常）。

- [ ] **Step 5: Commit**

```bash
git add frontend/tailwind.config.ts frontend/src/index.css frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat: enable tailwind dark mode class + add react-router-dom"
```

---

## Task 2：useTheme hook

**Files:**
- Create: `src/hooks/useTheme.ts`

- [ ] **Step 1: 创建 useTheme.ts**

```ts
// src/hooks/useTheme.ts
import { useEffect, useState } from "react";

type Theme = "light" | "dark";

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem("choreo-theme") as Theme) ?? "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    localStorage.setItem("choreo-theme", theme);
  }, [theme]);

  const toggle = () => setTheme((t) => (t === "light" ? "dark" : "light"));

  return { theme, toggle };
}
```

- [ ] **Step 2: 验证 hook 可导入（无 TS 报错）**

在任意 tsx 文件临时写 `import { useTheme } from "@/hooks/useTheme";`，确认 IDE 无红线，然后删除。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/hooks/useTheme.ts
git commit -m "feat: add useTheme hook with localStorage persistence"
```

---

## Task 3：Sidebar 组件

**Files:**
- Create: `src/components/Sidebar/Sidebar.tsx`

- [ ] **Step 1: 创建 Sidebar.tsx**

```tsx
// src/components/Sidebar/Sidebar.tsx
import { NavLink } from "react-router-dom";
import { useTheme } from "@/hooks/useTheme";

const NAV_ITEMS = [
  {
    to: "/chat",
    label: "新建对话",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <line x1="8" y1="3" x2="8" y2="13" /><line x1="3" y1="8" x2="13" y2="8" />
      </svg>
    ),
    exact: false,
  },
  {
    to: "/chat",
    label: "对话",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M2 3h12v9a1 1 0 01-1 1H3a1 1 0 01-1-1V3z" />
        <path d="M6 3V2a1 1 0 011-1h2a1 1 0 011 1v1" />
      </svg>
    ),
    exact: true,
  },
  {
    to: "/tasks",
    label: "定时任务",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <rect x="2" y="3" width="12" height="10" rx="1.5" />
        <line x1="5" y1="7" x2="11" y2="7" /><line x1="5" y1="10" x2="8" y2="10" />
      </svg>
    ),
    exact: true,
  },
  {
    to: "/history",
    label: "历史记录",
    icon: (
      <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="8" cy="8" r="5.5" /><polyline points="8 5 8 8 10 10" />
      </svg>
    ),
    exact: true,
  },
];

const RECENT_THREADS = [
  "每周五整理 commit 脚本",
  "自动化发布流程",
  "代码审查通知配置",
  "依赖更新检测脚本",
];

export default function Sidebar() {
  const { theme, toggle } = useTheme();

  return (
    <aside className="w-[230px] flex-shrink-0 flex flex-col h-full bg-[#ebe7df] dark:bg-[#141414] border-r border-[#ddd9d0] dark:border-[#202020]">
      {/* Logo */}
      <div className="flex items-center justify-between px-4 py-3">
        <span className="text-base font-bold tracking-tight text-[#0f0f0f] dark:text-[#e8e8e8]">
          Choreo
        </span>
        <button className="w-6 h-6 rounded flex items-center justify-center text-xs opacity-40 hover:opacity-70">
          ⊡
        </button>
      </div>

      {/* Nav */}
      <nav className="px-2 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.label}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-[13px] cursor-pointer transition-colors ${
                isActive && item.exact
                  ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                  : "text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8]"
              }`
            }
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Recent threads */}
      <div className="mt-3 px-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-[#aaa] dark:text-[#444]">
        最近对话
      </div>
      <div className="flex-1 overflow-hidden flex flex-col">
        {RECENT_THREADS.map((t) => (
          <button
            key={t}
            className="text-left px-4 py-1.5 text-[12px] text-[#666] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8] truncate"
          >
            {t}
          </button>
        ))}
      </div>

      {/* Footer */}
      <div className="px-3 py-2.5 border-t border-[#ddd9d0] dark:border-[#202020] flex items-center gap-2">
        <div className="w-[30px] h-[30px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white dark:text-[#e8e8e8] text-xs font-bold flex-shrink-0">
          U
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[12px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] truncate">用户</div>
          <div className="text-[10px] text-[#999] dark:text-[#444]">deepseek-chat</div>
        </div>
        {/* Theme toggle */}
        <div className="flex gap-0.5 bg-[#d6d0c7] dark:bg-[#1e1e1e] rounded-lg p-0.5">
          <button
            onClick={toggle}
            className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
              theme === "light"
                ? "bg-[#f0ede6] shadow-sm text-[#0f0f0f]"
                : "text-[#555]"
            }`}
          >☀️</button>
          <button
            onClick={toggle}
            className={`px-2 py-1 rounded-md text-[10px] transition-colors ${
              theme === "dark"
                ? "bg-[#2e2e2e] text-[#e8e8e8]"
                : "text-[#aaa]"
            }`}
          >🌙</button>
        </div>
      </div>
    </aside>
  );
}
```

- [ ] **Step 2: 确认 Sidebar 无 TS 错误**

```bash
cd frontend && pnpm tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Sidebar/Sidebar.tsx frontend/src/hooks/useTheme.ts
git commit -m "feat: add Sidebar component with theme toggle"
```

---

## Task 4：Topbar 组件

**Files:**
- Create: `src/components/Topbar/Topbar.tsx`

- [ ] **Step 1: 创建 Topbar.tsx**

```tsx
// src/components/Topbar/Topbar.tsx
interface TopbarProps {
  title: string;
  action?: React.ReactNode;
}

export default function Topbar({ title, action }: TopbarProps) {
  return (
    <div className="flex items-center justify-between px-5 py-2.5 border-b border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
      <span className="text-[13px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">
        {title}
      </span>
      {action ?? (
        <div className="flex items-center gap-1.5 bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555] dark:text-[#777] text-[11px] px-2.5 py-1 rounded-lg cursor-pointer">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />
          deepseek-chat ▾
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Topbar/Topbar.tsx
git commit -m "feat: add Topbar component"
```

---

## Task 5：App.tsx — 接入 react-router + 全局布局

**Files:**
- Modify: `src/App.tsx`
- Modify: `src/main.tsx`

- [ ] **Step 1: 修改 main.tsx，包裹 BrowserRouter**

```tsx
// src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
```

- [ ] **Step 2: 重写 App.tsx**

```tsx
// src/App.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar/Sidebar";
import ChatPage from "./pages/ChatPage";
import TaskListPage from "./pages/TaskListPage";
import HistoryPage from "./pages/HistoryPage";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/tasks" element={<TaskListPage />} />
          <Route path="/history" element={<HistoryPage />} />
        </Routes>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 验证路由可用**

```bash
cd frontend && pnpm dev
```

打开 http://localhost:5173，确认：
- 侧边栏出现在左侧
- URL `/` 自动跳转 `/chat`
- 点击侧边栏导航条目 URL 变化正常

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat: add react-router layout with Sidebar"
```

---

## Task 6：ChatMessage 组件重构

**Files:**
- Modify: `src/components/Chat/ChatMessage.tsx`

- [ ] **Step 1: 重写 ChatMessage.tsx**

AI 消息无气泡背景，直接渲染文字 + 左侧头像；用户消息深色气泡。

```tsx
// src/components/Chat/ChatMessage.tsx
import type { Message } from "@/store/chatStore";

interface Props { message: Message }

export default function ChatMessage({ message }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[68%] px-3.5 py-2.5 rounded-2xl rounded-br-[3px] bg-[#1e293b] dark:bg-[#2a2a2a] text-white dark:text-[#e8e8e8] text-[12.5px] leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.role === "system") {
    return (
      <div className="flex justify-center">
        <div className="text-[11px] text-[#aaa] dark:text-[#444] italic">{message.content}</div>
      </div>
    );
  }

  return (
    <div className="flex gap-2.5 items-start">
      <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
        🎼
      </div>
      <div className="text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8] whitespace-pre-wrap break-words max-w-[80%]">
        {message.content}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/ChatMessage.tsx
git commit -m "feat: redesign ChatMessage - no bubble for AI, dark user bubble"
```

---

## Task 7：ChatInput 组件重构

**Files:**
- Modify: `src/components/Chat/ChatInput.tsx`

- [ ] **Step 1: 重写 ChatInput.tsx**

```tsx
// src/components/Chat/ChatInput.tsx
import { useState, KeyboardEvent } from "react";

interface Props { onSend: (text: string) => void; disabled?: boolean }

export default function ChatInput({ onSend, disabled }: Props) {
  const [text, setText] = useState("");

  const handleSend = () => {
    if (!text.trim() || disabled) return;
    onSend(text.trim());
    setText("");
  };

  const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="px-6 pb-4 pt-3">
      <div className="max-w-[740px] mx-auto flex items-end gap-2.5 bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-[13px] px-3.5 py-2.5 shadow-sm dark:shadow-none">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKey}
          placeholder="描述你想自动化的任务，例如：每周五整理 commit 发飞书…"
          disabled={disabled}
          rows={2}
          className="flex-1 resize-none outline-none bg-transparent text-[12.5px] text-[#1a1a1a] dark:text-[#e8e8e8] placeholder-[#bbb] dark:placeholder-[#3a3a3a]"
        />
        <button
          onClick={handleSend}
          disabled={disabled || !text.trim()}
          className="w-7 h-7 rounded-lg bg-[#1e293b] dark:bg-[#252525] text-white dark:text-[#aaa] flex items-center justify-center text-sm flex-shrink-0 disabled:opacity-30 hover:opacity-80 transition-opacity"
        >
          ↑
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Chat/ChatInput.tsx
git commit -m "feat: redesign ChatInput with new layout"
```

---

## Task 8：ReviewPanel — 改为内嵌卡片

**Files:**
- Modify: `src/components/ReviewPanel/ReviewPanel.tsx`

HITL 审阅卡片从右侧侧边栏改为嵌入在聊天流底部的卡片。

- [ ] **Step 1: 重写 ReviewPanel.tsx**

```tsx
// src/components/ReviewPanel/ReviewPanel.tsx
import { useState } from "react";
import { useReview } from "@/hooks/useReview";
import type { Decision } from "@/types/review";

export default function ReviewPanel() {
  const { current, submitDecision } = useReview();
  const [loading, setLoading] = useState(false);

  if (!current) return null;

  const action = current.action_requests[0];
  const config = current.review_configs[0];
  const allowed = config?.allowed_decisions ?? ["approve", "reject"];

  const handle = async (type: Decision["type"]) => {
    setLoading(true);
    await submitDecision({ decisions: [{ type }] });
    setLoading(false);
  };

  return (
    <div className="max-w-[740px] mx-auto px-6 mb-3">
      <div className="rounded-xl p-3 bg-[#fefce8] dark:bg-[#1a1700] border border-[#fef08a] dark:border-[#2e2a00]">
        <div className="text-[11.5px] font-semibold text-[#713f12] dark:text-[#d4a017] mb-1.5 flex items-center gap-1.5">
          ⚠️ 需要确认：{action?.name}
        </div>
        {action?.description && (
          <p className="text-[10.5px] text-[#92400e] dark:text-[#a37a00] mb-1.5">{action.description}</p>
        )}
        <div className="font-mono text-[10.5px] bg-[#fef9c3] dark:bg-[#231e00] text-[#854d0e] dark:text-[#d4a017] px-2 py-1 rounded mb-2 inline-block">
          {JSON.stringify(action?.arguments)}
        </div>
        <div className="flex gap-2">
          {allowed.includes("approve") && (
            <button
              onClick={() => handle("approve")}
              disabled={loading}
              className="bg-green-600 text-white text-[11px] px-3 py-1 rounded-lg disabled:opacity-40 hover:bg-green-700"
            >
              ✓ 确认执行
            </button>
          )}
          {allowed.includes("reject") && (
            <button
              onClick={() => handle("reject")}
              disabled={loading}
              className="text-[11px] px-3 py-1 rounded-lg border border-[#fca5a5] dark:border-[#4a1515] text-red-600 dark:text-[#f87171] disabled:opacity-40"
            >
              ✕ 拒绝
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ReviewPanel/ReviewPanel.tsx
git commit -m "feat: ReviewPanel as inline chat card instead of sidebar panel"
```

---

## Task 9：ChatPage 重构

**Files:**
- Modify: `src/pages/ChatPage.tsx`

- [ ] **Step 1: 重写 ChatPage.tsx**

移除旧的侧边面板布局，改为全高度聊天区 + 底部输入框。

```tsx
// src/pages/ChatPage.tsx
import { useRef, useEffect } from "react";
import { ChatProvider, useChatStore } from "@/store/chatStore";
import { ReviewProvider } from "@/store/reviewStore";
import ChatMessage from "@/components/Chat/ChatMessage";
import ChatInput from "@/components/Chat/ChatInput";
import ReviewPanel from "@/components/ReviewPanel/ReviewPanel";
import Topbar from "@/components/Topbar/Topbar";
import { useChat } from "@/hooks/useChat";
import { useReviewStore } from "@/store/reviewStore";

function ChatInner() {
  const { messages, streamingContent } = useChatStore();
  const { sendMessage, streaming } = useChat();
  const { current: reviewRequest } = useReviewStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title={messages.length > 0 ? "当前对话" : "新对话"} />

      {/* 消息区 */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[740px] mx-auto px-6 py-5 flex flex-col gap-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-48 text-[#bbb] dark:text-[#333] text-sm gap-2">
              <span className="text-4xl">🎼</span>
              <span>告诉我你想自动化什么开发杂活</span>
            </div>
          )}
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          {streamingContent && (
            <div className="flex gap-2.5 items-start">
              <div className="w-[25px] h-[25px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white text-xs flex-shrink-0 mt-0.5">
                🎼
              </div>
              <div className="text-[12.5px] leading-[1.7] text-[#1a1a1a] dark:text-[#c8c8c8] max-w-[80%]">
                {streamingContent}
                <span className="inline-block w-0.5 h-4 bg-[#aaa] ml-0.5 animate-pulse align-middle" />
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* HITL 卡片 */}
      {reviewRequest && <ReviewPanel />}

      {/* 输入框 */}
      <div className="border-t border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
        <ChatInput
          onSend={sendMessage}
          disabled={streaming || !!reviewRequest}
        />
      </div>
    </div>
  );
}

export default function ChatPage() {
  return (
    <ChatProvider>
      <ReviewProvider>
        <ChatInner />
      </ReviewProvider>
    </ChatProvider>
  );
}
```

- [ ] **Step 2: 验证聊天页完整渲染**

```bash
cd frontend && pnpm dev
```

打开 http://localhost:5173/chat，确认：
- 顶栏显示"新对话"
- 空状态提示居中显示
- 输入框在底部，可以输入和发送
- 无 TS/控制台报错

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/ChatPage.tsx
git commit -m "feat: redesign ChatPage with new layout"
```

---

## Task 10：TaskListPage 重构

**Files:**
- Modify: `src/pages/TaskListPage.tsx`

- [ ] **Step 1: 重写 TaskListPage.tsx**

```tsx
// src/pages/TaskListPage.tsx
import { useEffect, useState } from "react";
import { getTasks, deleteTask, patchTask } from "@/api/tasks";
import Topbar from "@/components/Topbar/Topbar";
import type { Task } from "@/types/task";

export default function TaskListPage() {
  const [tasks, setTasks] = useState<Task[]>([]);

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
          <button className="text-[11px] px-2.5 py-1 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] text-[#555] dark:text-[#555] hover:opacity-80">
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
                <div className="flex-1 min-w-0">
                  <p className="text-[12.5px] font-medium text-[#0f0f0f] dark:text-[#e8e8e8] truncate">
                    {task.description}
                  </p>
                  <p className="text-[10.5px] text-[#aaa] dark:text-[#444] mt-0.5 truncate">
                    cron: {task.cron} · {task.script_path}
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
                  className="text-[10.5px] text-red-400 dark:text-[#4a1515] hover:text-red-600"
                >
                  删除
                </button>
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
git add frontend/src/pages/TaskListPage.tsx
git commit -m "feat: redesign TaskListPage with new layout"
```

---

## Task 11：HistoryPage 空状态

**Files:**
- Modify: `src/pages/HistoryPage.tsx`

- [ ] **Step 1: 重写 HistoryPage.tsx**

```tsx
// src/pages/HistoryPage.tsx
import Topbar from "@/components/Topbar/Topbar";

export default function HistoryPage() {
  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="历史记录" />
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center text-[#bbb] dark:text-[#333]">
          <div className="text-3xl mb-2">🕐</div>
          <p className="text-sm">暂无历史记录</p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 整体验收**

```bash
cd frontend && pnpm dev
```

逐一验证：
1. 访问 `/chat`：侧边栏 + 对话页正确渲染，dark/light 主题可切换，刷新后主题保持
2. 访问 `/tasks`：定时任务页顶栏显示"定时任务"，空状态提示正确
3. 访问 `/history`：历史记录空状态正确
4. 侧边栏 active 状态随路由变化正确高亮
5. 控制台无报错

- [ ] **Step 3: 最终 Commit**

```bash
git add frontend/src/pages/HistoryPage.tsx
git commit -m "feat: complete frontend redesign - Claude-style layout with dual theme"
```
