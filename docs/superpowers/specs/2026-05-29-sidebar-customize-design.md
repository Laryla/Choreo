# Sidebar 收起 + Customize 页面 设计文档

**日期：** 2026-05-29  
**状态：** 已审批

---

## 背景与目标

当前侧边栏是固定 230px 宽度，没有收起功能，且导航项随功能增加会越来越多。
需要：
1. 侧边栏支持收起，节省内容区宽度
2. 将「技能库」及未来的「MCP」等配置类功能统一收进 Customize 页面，主侧边栏只保留一个入口
3. Customize 页面风格参考 claude.ai/customize，左侧二级导航 + 右侧内容区

---

## 一、侧边栏收起

### 行为

| 状态 | 宽度 | 显示内容 |
|------|------|---------|
| 展开（默认） | 230px | Logo + 文字、新建对话（文字）、导航文字、最近对话列表、底部用户信息 |
| 收起 | 44px | 展开按钮 `›`、新建对话图标 `✏️`、导航图标、底部用户头像 |

### 交互细节

- **切换按钮**：展开态时，Header 右侧显示 `‹` 按钮；收起态时，顶部显示 `›` 按钮
- **动画**：`transition: width 200ms ease`，内容区同步用 `transition: margin-left 200ms ease` 跟随
- **收起后隐藏**：最近对话列表完全隐藏（不显示圆点或浮层）
- **Tooltip**：图标模式下，每个图标按钮加 `title` 属性作为 tooltip
- **状态持久化**：用 `localStorage.setItem('sidebar-collapsed', 'true/false')` 记录，刷新后恢复；默认值为 `false`（展开）

### 导航项变更

原来的「⚡ 技能库」从主侧边栏移除，改为「⚙️ 自定义」，路由指向 `/customize`。

```
展开态导航项：
  ✏️  新建对话
  ⏰  定时任务      → /tasks
  📋  历史记录      → /history
  ⚙️  自定义        → /customize

收起态图标（从上到下）：
  ›          展开按钮
  ✏️         新建对话
  ⏰         定时任务
  📋         历史记录
  ⚙️         自定义（高亮：active 时黄色 #e2b714）
  [头像]     用户（底部）
```

### 实现方式

- `Sidebar.tsx` 新增 `collapsed` state（从 localStorage 初始化）
- 顶层 `div` 的 `className` 根据 `collapsed` 切换 `w-[230px]` / `w-[44px]`，加 `transition-[width] duration-200`
- 导航文字、对话列表用 `collapsed && 'hidden'` 控制显隐
- 图标始终渲染，展开态时和文字一起显示，收起态时单独显示

---

## 二、Customize 页面

### 路由结构

```
/customize            → redirect to /customize/skills
/customize/skills     → 技能库（迁移原 SkillsPage 内容）
/customize/mcp        → MCP 占位页
```

原来的 `/skills` 路由保留重定向到 `/customize/skills`，避免已有链接失效。

### 页面布局（三列）

```
┌─────────┬───────────────┬──────────────────────────────┐
│ 主侧边栏 │  二级导航      │  内容区                       │
│ 44px    │  200px        │  flex-1                       │
│（图标）  │               │                               │
│         │  自定义         │  ⚡ 技能库                    │
│ ✏️      │  ─────────    │  管理 AI 助手的专项技能         │
│ ⏰      │  ⚡ 技能库  ←  │  ────────────────────────    │
│ 📋      │  🔌 MCP 即将  │  [当前] [归档]  搜索  [+新建]  │
│ ⚙️ ←   │               │                               │
│         │               │  git                          │
│ [头像]  │               │  ├ 周报生成器                  │
└─────────┴───────────────┴──────────────────────────────┘
```

### 二级导航（CustomizeNav）

独立组件 `CustomizeNav.tsx`，放在 `components/Customize/` 目录下。

```
⚡ 技能库          → /customize/skills   （active 高亮）
🔌 MCP 连接器     → /customize/mcp      （显示「即将推出」badge）
```

- 样式：背景 `#0f0f0f`，宽 200px，顶部有 `CUSTOMIZE` 小标题（monospace uppercase）
- active 项：背景 `#1c1c1c`，文字 `#e8e8e8`
- 非 active 项：文字 `#666`，hover `#181818`

### 技能库页面（/customize/skills）

直接复用现有 `SkillsPage.tsx` 的内容，但去掉外层的独立页面包裹（Topbar、全屏容器），改为内嵌到 Customize 布局的内容区里。

- Header 区域：标题「⚡ 技能库」+ 副标题描述
- 工具栏：当前/归档 Tab + 搜索框 + 新建按钮（保持原逻辑）
- 卡片列表：复用 `SkillCard` 组件

### MCP 占位页（/customize/mcp）

简单占位，不做实际功能：

```
🔌

MCP 连接器即将推出
允许 AI 助手连接外部工具和数据源

[了解更多]（链接到 MCP 文档，暂时不加）
```

---

## 三、文件改动清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/pages/CustomizePage.tsx` | Customize 页面容器（三列布局） |
| `frontend/src/components/Customize/CustomizeNav.tsx` | 二级导航组件 |
| `frontend/src/pages/CustomizeSkillsPage.tsx` | 技能库内嵌页（复用 SkillsPage 内容） |
| `frontend/src/pages/CustomizeMcpPage.tsx` | MCP 占位页 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `frontend/src/components/Sidebar/Sidebar.tsx` | 新增 collapsed 状态、切换按钮、图标模式渲染 |
| `frontend/src/App.tsx` | 新增 `/customize/*` 路由，`/skills` 重定向，保留旧路由兼容 |

### 可删除（迁移完成后）

| 文件 | 说明 |
|------|------|
| `frontend/src/pages/SkillsPage.tsx` | 内容迁移到 CustomizeSkillsPage 后可删除 |

---

## 四、验收标准

1. 侧边栏点击 `‹` / `›` 按钮平滑切换，宽度动画正常
2. 收起态：只显示图标，无文字，无对话列表
3. 刷新页面：侧边栏状态与上次一致
4. 点击 `⚙️ 自定义` 进入 `/customize/skills`，显示技能库内容
5. Customize 二级导航：点击「技能库」/ 「MCP」正确切换路由
6. MCP 页面显示占位内容，不报错
7. `/skills` 旧路由重定向到 `/customize/skills`
8. 原技能库 CRUD 功能（新建、编辑、归档、删除）在新路由下正常工作
