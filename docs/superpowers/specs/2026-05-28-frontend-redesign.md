# Choreo 前端重设计规格

## 概述

将现有前端从顶部导航 Tab 布局重构为 Claude 风格的侧边栏布局，支持亮色/暗色双主题切换，配色采用中性黑（Slate）风格。

---

## 设计决策

| 维度 | 决策 |
|---|---|
| 布局 | Claude 风格：左侧固定侧边栏 + 居中内容区 |
| 主题 | 双主题（Light / Dark），运行时一键切换，`localStorage` 持久化 |
| 主题色 | 中性黑 Slate（无彩色主色，极简风格，参考 Notion） |
| 导航结构 | 侧边栏图标+文字条目，替代原顶部 Tab |
| HITL 审阅 | 内嵌于聊天流中（卡片形式），不用弹窗 |
| 工具调用展示 | 内联 badge（`✓ tool_name · 说明`） |

---

## 布局结构

```
┌─────────────────────────────────────────────────────┐
│  Sidebar (230px)          │  Main Content Area       │
│                           │                          │
│  [Logo]         [Collapse]│  [Topbar: 标题 | 模型]   │
│  ─────────────────────    │  ─────────────────────── │
│  + 新建对话               │                          │
│  🔍 搜索                  │   消息列表 / 页面内容    │
│  💬 对话       ← active   │   (max-width: 740px,     │
│  ⏰ 定时任务              │    margin: 0 auto)       │
│  🕐 历史记录              │                          │
│  ⚙️ 设置                  │                          │
│  ─────────────────────    │  [HITL 审阅卡片]         │
│  最近对话                 │  ─────────────────────── │
│    每周五整理…            │  [输入框]                │
│    自动化发布…            │                          │
│  ─────────────────────    │                          │
│  [Avatar] 用户  [☀️/🌙]  │                          │
└─────────────────────────────────────────────────────┘
```

---

## 颜色 Token

### Light 主题

| Token | 值 | 用途 |
|---|---|---|
| `--bg-base` | `#f5f2eb` | 主内容区背景 |
| `--bg-sidebar` | `#ebe7df` | 侧边栏背景 |
| `--bg-topbar` | `#f0ede6` | 顶栏背景 |
| `--bg-card` | `#ffffff` | 卡片/输入框背景 |
| `--border` | `#ddd9d0` | 边框 |
| `--text-primary` | `#0f0f0f` | 主文字 |
| `--text-secondary` | `#666666` | 次级文字 |
| `--text-muted` | `#aaaaaa` | 辅助文字 |
| `--nav-active-bg` | `#d6d0c7` | 导航激活背景 |
| `--bubble-user` | `#1e293b` | 用户消息气泡 |
| `--bubble-user-text` | `#ffffff` | 用户消息文字 |
| `--send-btn` | `#1e293b` | 发送按钮 |

### Dark 主题

| Token | 值 | 用途 |
|---|---|---|
| `--bg-base` | `#141414` | 主内容区背景 |
| `--bg-sidebar` | `#141414` | 侧边栏背景 |
| `--bg-topbar` | `#141414` | 顶栏背景 |
| `--bg-card` | `#1a1a1a` | 卡片/输入框背景 |
| `--border` | `#202020` | 边框 |
| `--text-primary` | `#e8e8e8` | 主文字 |
| `--text-secondary` | `#999999` | 次级文字 |
| `--text-muted` | `#444444` | 辅助文字 |
| `--nav-active-bg` | `#1e1e1e` | 导航激活背景 |
| `--bubble-user` | `#2a2a2a` | 用户消息气泡 |
| `--bubble-user-text` | `#e8e8e8` | 用户消息文字 |
| `--send-btn` | `#252525` | 发送按钮 |

---

## 组件规格

### Sidebar

- 宽度：230px，固定不滚动
- Logo：文字 "Choreo" + 右侧收起按钮（预留，暂不实现收起功能）
- 导航条目：图标（16×16 SVG）+ 文字，`padding: 7px 9px`，`border-radius: 7px`
- 激活状态：加重背景色 + 字重 500
- 分区标题：`最近对话`，全大写，字号 10px，灰色
- 最近对话：最多显示 10 条，单行截断，点击进入对应对话
- 底部用户区：头像（首字母）+ 用户名 + 当前模型名 + 主题切换按钮

### 主题切换按钮

位于侧边栏底部，☀️ / 🌙 两个 pill，当前主题高亮。切换时：
1. 切换 `<html>` 上的 `data-theme="light|dark"` 属性
2. 写入 `localStorage.setItem('choreo-theme', theme)`
3. 页面初始化时读取并应用

### 顶栏（Topbar）

- 左侧：当前对话标题（对话页）或页面名称（其他页）
- 右侧：模型选择器 pill（绿点 + 模型名 + ▾），点击后预留下拉扩展

### 消息区（ChatPage）

- 最大宽度 740px，`margin: 0 auto`，两侧留白
- 用户消息：右对齐，深色气泡（`border-radius: 16px 16px 3px 16px`）
- AI 消息：左对齐，无气泡背景，直接渲染文字，左侧 25px 圆形头像
- 工具调用 badge：`✓ tool_name · 结果摘要`，灰色小标签，inline 展示

### HITL 审阅卡片

嵌入在消息流底部（不是弹窗），样式：
- Light：`#fefce8` 背景，`#fef08a` 边框，黄色调
- Dark：`#1a1700` 背景，`#2e2a00` 边框
- 内容：标题 + monospace 命令行 + 确认/拒绝按钮
- 卡片展示时输入框禁用

### 输入框

- 最大宽度 740px，`margin: 0 auto`
- 圆角卡片，`border-radius: 13px`
- `textarea`（可多行，Shift+Enter 换行，Enter 发送）
- 右侧发送按钮（↑ 图标）

### 定时任务页（TaskListPage）

- 无独立输入框，顶栏右侧有「+ 新建任务」按钮
- 任务卡片：名称 + cron 表达式 + 脚本路径 + 状态 badge + 暂停/删除操作
- 状态 badge：运行中（绿色）/ 已暂停（灰色）

### 历史记录页（HistoryPage）

- 列表展示历史 run 记录：时间 + 关联对话标题 + 执行状态
- 暂为空状态占位（功能待后端实现）

---

## 文件结构变更

```
frontend/src/
├── styles/
│   └── theme.css          # CSS 变量定义（--bg-base 等 token）
├── components/
│   ├── Sidebar/
│   │   └── Sidebar.tsx    # 侧边栏组件
│   ├── Topbar/
│   │   └── Topbar.tsx     # 顶栏组件
│   ├── Chat/
│   │   ├── ChatMessage.tsx
│   │   └── ChatInput.tsx
│   └── ReviewPanel/
│       └── ReviewPanel.tsx  # 重构为内嵌卡片
├── hooks/
│   └── useTheme.ts        # 主题切换 hook（读写 localStorage）
├── pages/
│   ├── ChatPage.tsx
│   ├── TaskListPage.tsx
│   └── HistoryPage.tsx
└── App.tsx                # 路由改为 path-based，渲染 Sidebar
```

---

## 路由方案

从 `useState` 切换 page 改为基于 path 的路由（使用 `react-router-dom`）：

```
/          → ChatPage（重定向到 /chat）
/chat      → ChatPage
/tasks     → TaskListPage
/history   → HistoryPage
```

侧边栏导航条目点击时 `navigate(path)`，`useLocation` 判断激活状态。

---

## 不在本次范围内

- 侧边栏收起/展开动画
- 模型选择下拉菜单
- 历史记录后端 API
- 搜索功能
- 用户认证/头像

---

## 验收标准

1. Light/Dark 双主题可切换，刷新后保持
2. 侧边栏导航正确高亮当前页
3. 对话页：消息流式渲染、HITL 卡片展示、输入框发送正常
4. 定时任务页：任务列表展示、暂停/删除操作正常
5. 响应式：宽度 ≥ 1024px 正常显示（不要求移动端适配）
