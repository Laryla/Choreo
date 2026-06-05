# Sidebar 收起 + Customize 页面 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 侧边栏支持图标模式收起，并将「技能库」迁移进新的 Customize 三列页面（参考 claude.ai/customize 风格），MCP 占位预留。

**Architecture:** Sidebar 新增 `collapsed` state（localStorage 持久化），展开时 230px，收起时 44px 图标模式；App.tsx 增加 `/customize/*` 嵌套路由；CustomizePage 由 CustomizeNav（200px 二级导航）+ 内容区组成，内容区内嵌 CustomizeSkillsPage / CustomizeMcpPage。

**Tech Stack:** React 18、React Router v6、Tailwind CSS、SWR（技能库数据层不变）

---

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `frontend/src/components/Sidebar/Sidebar.tsx` | 新增 collapsed 状态、切换按钮、图标模式渲染、导航项改为自定义 |
| 修改 | `frontend/src/App.tsx` | 增加 `/customize/*` 路由，`/skills` 重定向 |
| 新建 | `frontend/src/components/Customize/CustomizeNav.tsx` | 自定义二级导航（200px） |
| 新建 | `frontend/src/pages/CustomizePage.tsx` | Customize 容器（CustomizeNav + 内容嵌套路由） |
| 新建 | `frontend/src/pages/CustomizeSkillsPage.tsx` | 技能库内容页（从 SkillsPage 内容提取，去掉 Topbar） |
| 新建 | `frontend/src/pages/CustomizeMcpPage.tsx` | MCP 占位页 |
| 删除 | `frontend/src/pages/SkillsPage.tsx` | 内容迁移后删除（路由已重定向） |

---

## Task 1：Sidebar 收起状态与切换按钮

**Files:**
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`

- [ ] **Step 1：在 Sidebar 顶部加入 collapsed 状态**

在 `export default function Sidebar()` 函数体最开头，原有的三行 hooks 之后插入：

```tsx
const [collapsed, setCollapsed] = useState<boolean>(
  () => localStorage.getItem("sidebar-collapsed") === "true"
);

const toggleCollapsed = () => {
  setCollapsed((prev) => {
    localStorage.setItem("sidebar-collapsed", String(!prev));
    return !prev;
  });
};
```

同时在文件顶部 import 里补上 `useState`（原来没有）：

```tsx
import { useState } from "react";
import useSWR from "swr";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { useTheme } from "@/hooks/useTheme";
import { THREADS_KEY } from "@/hooks/useChat";
```

- [ ] **Step 2：`<aside>` 宽度改为响应 collapsed**

将：
```tsx
<aside className="w-[230px] flex-shrink-0 flex flex-col h-full bg-[#ebe7df] dark:bg-[#141414] border-r border-[#ddd9d0] dark:border-[#202020]">
```
改为：
```tsx
<aside className={`flex-shrink-0 flex flex-col h-full bg-[#ebe7df] dark:bg-[#141414] border-r border-[#ddd9d0] dark:border-[#202020] transition-[width] duration-200 ease-in-out overflow-hidden ${collapsed ? "w-[44px]" : "w-[230px]"}`}>
```

- [ ] **Step 3：Header 区域改为展开/收起切换按钮**

将原来的 Header（第 57-64 行）整体替换：

```tsx
{/* Logo / Header */}
{collapsed ? (
  <div className="flex items-center justify-center px-0 py-3 border-b border-[#ddd9d0] dark:border-[#202020]">
    <button
      onClick={toggleCollapsed}
      title="展开侧边栏"
      className="w-7 h-7 rounded flex items-center justify-center text-[13px] text-[#aaa] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8] transition-colors"
    >
      ›
    </button>
  </div>
) : (
  <div className="flex items-center justify-between px-4 py-3">
    <span className="text-base font-bold tracking-tight text-[#0f0f0f] dark:text-[#e8e8e8] whitespace-nowrap">
      Choreo
    </span>
    <button
      onClick={toggleCollapsed}
      title="收起侧边栏"
      className="w-6 h-6 rounded flex items-center justify-center text-[12px] text-[#aaa] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8] transition-colors"
    >
      ‹
    </button>
  </div>
)}
```

- [ ] **Step 4：新建对话按钮收起模式只显示图标**

将原来的 "New chat button" 区块（第 66-77 行）替换：

```tsx
{/* New chat button */}
<div className={`${collapsed ? "px-1.5 py-2 flex justify-center" : "px-2 mb-1"}`}>
  <button
    onClick={() => navigate("/chat")}
    title="新建对话"
    className={`flex items-center gap-2.5 rounded-lg text-[13px] cursor-pointer transition-colors text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8] ${
      collapsed ? "w-8 h-8 justify-center" : "w-full px-2.5 py-1.5"
    }`}
  >
    <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <line x1="8" y1="3" x2="8" y2="13" /><line x1="3" y1="8" x2="13" y2="8" />
    </svg>
    {!collapsed && <span>新建对话</span>}
  </button>
</div>
```

- [ ] **Step 5：Nav 收起模式只显示图标**

将 Nav 区块（第 79-97 行）替换：

```tsx
{/* Nav */}
<nav className={`flex flex-col gap-0.5 ${collapsed ? "px-1.5 items-center" : "px-2"}`}>
  {NAV_ITEMS.map((item) => (
    <NavLink
      key={item.label}
      to={item.to}
      title={item.label}
      className={({ isActive }) =>
        `flex items-center transition-colors rounded-lg cursor-pointer ${
          collapsed
            ? `w-8 h-8 justify-center ${isActive ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8]" : "text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e]"}`
            : `gap-2.5 px-2.5 py-1.5 text-[13px] ${isActive ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8] font-medium" : "text-[#3a3a3a] dark:text-[#999] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] dark:hover:text-[#e8e8e8]"}`
        }`
      }
    >
      {item.icon}
      {!collapsed && <span>{item.label}</span>}
    </NavLink>
  ))}
</nav>
```

- [ ] **Step 6：最近对话区域收起时完全隐藏**

将 "Recent threads" 标题行（第 100 行）加条件：

```tsx
{!collapsed && (
  <div className="mt-3 px-4 pb-1 text-[10px] font-semibold uppercase tracking-wider text-[#aaa] dark:text-[#444]">
    最近对话
  </div>
)}
{!collapsed && (
  <div className="flex-1 overflow-y-auto flex flex-col">
    {threads.length === 0 ? (
      <p className="px-4 py-2 text-[11px] text-[#bbb] dark:text-[#333]">暂无对话</p>
    ) : (
      threads.slice(0, 20).map((t) => (
        <button
          key={t.thread_id}
          onClick={() => navigate(`/chat/${t.thread_id}`)}
          className={`text-left px-4 py-1.5 text-[12px] truncate flex items-center gap-2 transition-colors ${
            activeThreadId === t.thread_id
              ? "bg-[#d6d0c7] dark:bg-[#1e1e1e] text-[#0f0f0f] dark:text-[#e8e8e8]"
              : "text-[#666] dark:text-[#555] hover:bg-[#ddd9d0] dark:hover:bg-[#1e1e1e] hover:text-[#0f0f0f] dark:hover:text-[#e8e8e8]"
          }`}
        >
          <span className="truncate">{t.title ?? `对话 ${t.thread_id.slice(0, 8)}`}</span>
          {t.status === "interrupted" && (
            <span className="text-[9px] text-amber-500 flex-shrink-0">●</span>
          )}
        </button>
      ))
    )}
  </div>
)}
{collapsed && <div className="flex-1" />}
```

- [ ] **Step 7：Footer 收起模式只显示头像**

将 Footer 区块（第 127-154 行）替换：

```tsx
{/* Footer */}
<div className={`border-t border-[#ddd9d0] dark:border-[#202020] flex items-center ${collapsed ? "justify-center py-2.5" : "gap-2 px-3 py-2.5"}`}>
  <div className="w-[30px] h-[30px] rounded-full bg-[#1e293b] dark:bg-[#2a2a2a] flex items-center justify-center text-white dark:text-[#e8e8e8] text-xs font-bold flex-shrink-0">
    U
  </div>
  {!collapsed && (
    <>
      <div className="flex-1 min-w-0">
        <div className="text-[12px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] truncate">用户</div>
        <div className="text-[10px] text-[#999] dark:text-[#444]">deepseek-chat</div>
      </div>
      <div className="flex gap-0.5 bg-[#d6d0c7] dark:bg-[#1e1e1e] rounded-lg p-0.5">
        <button
          onClick={setLight}
          className={`px-2 py-1 rounded-md text-[10px] transition-colors ${theme === "light" ? "bg-[#f0ede6] shadow-sm text-[#0f0f0f]" : "text-[#555]"}`}
        >☀️</button>
        <button
          onClick={setDark}
          className={`px-2 py-1 rounded-md text-[10px] transition-colors ${theme === "dark" ? "bg-[#2e2e2e] text-[#e8e8e8]" : "text-[#aaa]"}`}
        >🌙</button>
      </div>
    </>
  )}
</div>
```

- [ ] **Step 8：启动前端验证**

```bash
cd frontend && pnpm dev
```

验证：
- 默认侧边栏展开（230px），显示文字 + 对话列表
- 点击 `‹` → 收起为 44px，仅图标，无文字，无对话列表，有动画
- 点击 `›` → 展开恢复
- 刷新页面 → 状态与上次一致

- [ ] **Step 9：提交**

```bash
git add frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat(sidebar): add collapsible icon mode with localStorage persistence"
```

---

## Task 2：Sidebar 导航项「技能库」→「⚙️ 自定义」

**Files:**
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`

- [ ] **Step 1：修改 NAV_ITEMS**

将文件顶部 `NAV_ITEMS` 数组中的「技能库」项：

```tsx
{
  to: "/skills",
  label: "技能库",
  icon: (
    <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 2h10v12H3z" />
      <line x1="5" y1="5" x2="11" y2="5" />
      <line x1="5" y1="8" x2="11" y2="8" />
      <line x1="5" y1="11" x2="8" y2="11" />
    </svg>
  ),
},
```

替换为：

```tsx
{
  to: "/customize",
  label: "自定义",
  icon: (
    <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="8" cy="8" r="2.5" />
      <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" />
    </svg>
  ),
},
```

注意：`isActive` 匹配 `/customize` 时自动高亮（React Router NavLink 默认前缀匹配，需要加 `end={false}` 让 `/customize/skills` 也高亮）。

在 NavLink 上增加 `end={false}`（仅对「自定义」项需要，其他项默认即可）。由于 `NAV_ITEMS` 是通用渲染，在 NavLink 属性里加一个条件：

```tsx
<NavLink
  key={item.label}
  to={item.to}
  end={item.to !== "/customize"}   // 新增这一行
  title={item.label}
  ...
>
```

- [ ] **Step 2：验证高亮**

启动 `pnpm dev`，访问 `/customize/skills`，确认侧边栏「自定义」项高亮。

- [ ] **Step 3：提交**

```bash
git add frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat(sidebar): replace skills nav with customize entry"
```

---

## Task 3：CustomizeNav 二级导航组件

**Files:**
- Create: `frontend/src/components/Customize/CustomizeNav.tsx`

- [ ] **Step 1：创建文件**

```tsx
// frontend/src/components/Customize/CustomizeNav.tsx
import { NavLink } from "react-router-dom";

const ITEMS = [
  {
    to: "/customize/skills",
    label: "技能库",
    icon: (
      <svg className="w-4 h-4 flex-shrink-0 opacity-70" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <path d="M3 2h10v12H3z" />
        <line x1="5" y1="5" x2="11" y2="5" />
        <line x1="5" y1="8" x2="11" y2="8" />
        <line x1="5" y1="11" x2="8" y2="11" />
      </svg>
    ),
    comingSoon: false,
  },
  {
    to: "/customize/mcp",
    label: "MCP 连接器",
    icon: (
      <svg className="w-4 h-4 flex-shrink-0 opacity-70" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
        <circle cx="5" cy="8" r="2" />
        <circle cx="11" cy="4" r="2" />
        <circle cx="11" cy="12" r="2" />
        <line x1="7" y1="7" x2="9" y2="5" />
        <line x1="7" y1="9" x2="9" y2="11" />
      </svg>
    ),
    comingSoon: true,
  },
];

export default function CustomizeNav() {
  return (
    <nav className="w-[200px] flex-shrink-0 h-full bg-[#f0ede6] dark:bg-[#0f0f0f] border-r border-[#ddd9d0] dark:border-[#1a1a1a] flex flex-col pt-5 px-3">
      <div className="text-[10px] text-[#bbb] dark:text-[#3a3a3a] uppercase tracking-[0.08em] font-mono mb-3 px-2">
        自定义
      </div>
      <div className="flex flex-col gap-0.5">
        {ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-2.5 py-[7px] rounded-lg text-[12.5px] cursor-pointer transition-colors ${
                isActive
                  ? "bg-[#e5e1d8] dark:bg-[#1c1c1c] text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                  : "text-[#666] dark:text-[#666] hover:bg-[#e8e4dc] dark:hover:bg-[#181818] hover:text-[#1a1a1a] dark:hover:text-[#ccc]"
              }`
            }
          >
            {item.icon}
            <span className="flex-1">{item.label}</span>
            {item.comingSoon && (
              <span className="text-[9px] text-[#aaa] dark:text-[#333] border border-[#ddd] dark:border-[#2a2a2a] rounded px-1 font-mono">
                即将推出
              </span>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
```

- [ ] **Step 2：提交**

```bash
git add frontend/src/components/Customize/CustomizeNav.tsx
git commit -m "feat(customize): add CustomizeNav secondary navigation component"
```

---

## Task 4：CustomizeSkillsPage（技能库内容页）

**Files:**
- Create: `frontend/src/pages/CustomizeSkillsPage.tsx`

- [ ] **Step 1：创建文件**

从 `SkillsPage.tsx` 提取内容，去掉 `Topbar`，加上内容区 header：

```tsx
// frontend/src/pages/CustomizeSkillsPage.tsx
import { useState } from "react";
import useSWR from "swr";
import SkillCard from "@/components/Skills/SkillCard";
import SkillEditor from "@/components/Skills/SkillEditor";
import type { Skill } from "@/api/skills";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
type Tab = "active" | "archived";

export default function CustomizeSkillsPage() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Tab>("active");
  const [editTarget, setEditTarget] = useState<Skill | null | undefined>(undefined);

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tab === "archived") params.set("state", "archived");
  const swrKey = `/api/skills/?${params.toString()}`;

  const { data: skills = [], mutate } = useSWR<Skill[]>(
    swrKey,
    (url: string) => fetch(`${API}${url}`).then((r) => r.json())
  );

  const refresh = () => mutate();
  const categories = [...new Set(skills.map((s) => s.category))].sort();

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#0d0d0d]">
      {/* Content header */}
      <div className="px-7 pt-6 pb-4 border-b border-[#ddd9d0] dark:border-[#141414]">
        <h1 className="text-[17px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] mb-1">技能库</h1>
        <p className="text-[12px] text-[#999] dark:text-[#555]">管理 AI 助手的专项技能，技能会在对话中被自动调用</p>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2.5 px-7 py-3 border-b border-[#ddd9d0] dark:border-[#141414] bg-[#f0ede6] dark:bg-[#0d0d0d]">
        <div className="flex gap-1">
          {(["active", "archived"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-lg text-[11.5px] transition-colors ${
                tab === t
                  ? "bg-[#1e293b] dark:bg-[#2a2a2a] text-white"
                  : "text-[#666] dark:text-[#888] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e]"
              }`}
            >
              {t === "active" ? "当前" : "归档"}
            </button>
          ))}
        </div>
        <input
          className="flex-1 max-w-xs px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none"
          placeholder="搜索技能…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <button
          onClick={() => setEditTarget(null)}
          className="ml-auto px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors"
        >
          + 新建技能
        </button>
      </div>

      {/* Skills list */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[860px] mx-auto px-7 py-5">
          {skills.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-[#bbb] dark:text-[#333] text-sm gap-2">
              <span className="text-4xl">⚡</span>
              <span>{q ? "没有匹配的技能" : "还没有技能，点击右上角新建"}</span>
            </div>
          ) : (
            categories.map((cat) => (
              <div key={cat} className="mb-6">
                <h3 className="text-[11px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wider mb-2 font-mono">
                  {cat}/
                </h3>
                <div className="flex flex-col gap-2">
                  {skills
                    .filter((s) => s.category === cat)
                    .map((skill) => (
                      <SkillCard
                        key={skill.id}
                        skill={skill}
                        onUpdate={refresh}
                        onDelete={refresh}
                        onEdit={(s) => setEditTarget(s)}
                      />
                    ))}
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {editTarget !== undefined && (
        <SkillEditor
          skill={editTarget}
          onSave={() => { refresh(); setEditTarget(undefined); }}
          onClose={() => setEditTarget(undefined)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2：提交**

```bash
git add frontend/src/pages/CustomizeSkillsPage.tsx
git commit -m "feat(customize): add CustomizeSkillsPage extracted from SkillsPage"
```

---

## Task 5：CustomizeMcpPage（MCP 占位页）

**Files:**
- Create: `frontend/src/pages/CustomizeMcpPage.tsx`

- [ ] **Step 1：创建文件**

```tsx
// frontend/src/pages/CustomizeMcpPage.tsx
export default function CustomizeMcpPage() {
  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#0d0d0d]">
      {/* Content header */}
      <div className="px-7 pt-6 pb-4 border-b border-[#ddd9d0] dark:border-[#141414]">
        <h1 className="text-[17px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8] mb-1">MCP 连接器</h1>
        <p className="text-[12px] text-[#999] dark:text-[#555]">允许 AI 助手连接外部工具和数据源</p>
      </div>

      {/* Placeholder */}
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-8">
        <div className="text-5xl opacity-20">🔌</div>
        <div className="text-[15px] font-medium text-[#aaa] dark:text-[#444]">MCP 连接器即将推出</div>
        <div className="text-[12px] text-[#bbb] dark:text-[#333] max-w-xs leading-relaxed">
          MCP（Model Context Protocol）让 AI 助手能够安全地连接数据库、API 和本地工具。
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2：提交**

```bash
git add frontend/src/pages/CustomizeMcpPage.tsx
git commit -m "feat(customize): add CustomizeMcpPage placeholder"
```

---

## Task 6：CustomizePage 容器（三列布局）

**Files:**
- Create: `frontend/src/pages/CustomizePage.tsx`

- [ ] **Step 1：创建文件**

```tsx
// frontend/src/pages/CustomizePage.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import CustomizeNav from "@/components/Customize/CustomizeNav";
import CustomizeSkillsPage from "./CustomizeSkillsPage";
import CustomizeMcpPage from "./CustomizeMcpPage";

export default function CustomizePage() {
  return (
    <div className="flex h-full overflow-hidden">
      <CustomizeNav />
      <div className="flex-1 min-w-0 overflow-hidden">
        <Routes>
          <Route index element={<Navigate to="skills" replace />} />
          <Route path="skills" element={<CustomizeSkillsPage />} />
          <Route path="mcp" element={<CustomizeMcpPage />} />
        </Routes>
      </div>
    </div>
  );
}
```

- [ ] **Step 2：提交**

```bash
git add frontend/src/pages/CustomizePage.tsx
git commit -m "feat(customize): add CustomizePage three-column layout container"
```

---

## Task 7：App.tsx 路由更新

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1：更新 App.tsx**

将整个文件替换为：

```tsx
import { Navigate, Route, Routes } from "react-router-dom";
import Sidebar from "./components/Sidebar/Sidebar";
import ChatPage from "./pages/ChatPage";
import TaskListPage from "./pages/TaskListPage";
import HistoryPage from "./pages/HistoryPage";
import CustomizePage from "./pages/CustomizePage";

export default function App() {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:threadId" element={<ChatPage />} />
          <Route path="/tasks" element={<TaskListPage />} />
          <Route path="/history" element={<HistoryPage />} />
          {/* /skills 兼容旧链接，重定向到新路由 */}
          <Route path="/skills" element={<Navigate to="/customize/skills" replace />} />
          <Route path="/customize/*" element={<CustomizePage />} />
        </Routes>
      </div>
    </div>
  );
}
```

- [ ] **Step 2：验证全链路**

```bash
cd frontend && pnpm dev
```

验证清单：
1. 访问 `/customize` → 自动跳转到 `/customize/skills`，显示技能库内容
2. 侧边栏「自定义」项高亮
3. CustomizeNav 左侧「技能库」高亮
4. 点击 CustomizeNav「MCP 连接器」→ 跳转 `/customize/mcp`，显示占位页
5. 访问旧 `/skills` → 自动重定向到 `/customize/skills`
6. 技能库新建、编辑、归档、删除功能正常
7. 侧边栏收起后，访问 Customize 三列布局正常（主侧边栏 44px + CustomizeNav 200px + 内容区）

- [ ] **Step 3：删除 SkillsPage.tsx**

```bash
rm frontend/src/pages/SkillsPage.tsx
```

- [ ] **Step 4：提交**

```bash
git add frontend/src/App.tsx
git add -u frontend/src/pages/SkillsPage.tsx   # 记录删除
git commit -m "feat(customize): wire up /customize routes, redirect /skills, remove SkillsPage"
```

---

## 自检结果

**Spec 覆盖：**
- ✅ 侧边栏 44px 图标收起（Task 1）
- ✅ Header `‹/›` 按钮切换（Task 1 Step 3）
- ✅ 收起后对话列表隐藏（Task 1 Step 6）
- ✅ 默认展开 + localStorage 持久化（Task 1 Step 1）
- ✅ 新建对话收起后图标（Task 1 Step 4）
- ✅ 「技能库」→「⚙️ 自定义」（Task 2）
- ✅ Customize 三列布局（Task 6）
- ✅ CustomizeNav 二级导航（Task 3）
- ✅ `/customize/skills` 技能库内容（Task 4）
- ✅ `/customize/mcp` 占位页（Task 5）
- ✅ `/skills` 旧路由重定向（Task 7）
- ✅ 技能库 CRUD 功能保留（Task 4 使用相同的 SWR + SkillCard + SkillEditor）

**Placeholder 扫描：** 无 TBD / TODO

**类型一致性：** `Skill` 类型来自 `@/api/skills`，CustomizeSkillsPage 与原 SkillsPage 用法完全一致
