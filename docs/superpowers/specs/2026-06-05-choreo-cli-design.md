# Choreo CLI 设计文档

## 概述

为 Choreo 项目新增一个 TypeScript 命令行 CLI，风格类似 Claude Code，与现有 Web UI 并存。CLI 连接同一套 FastAPI 后端，无需修改后端代码。

---

## 设计决策

| 维度 | 决定 | 说明 |
|------|------|------|
| 整体风格 | Claude Code 风 | 有颜色、有框、顶部状态行 |
| 思考块 | 折叠摘要 | 思考结束后收成 `💭 已思考 N 步 ▶`，可回车展开 |
| 状态栏 | 标准 | `◉ Choreo · <branch> · <model>` |
| 主题色 | 用户自选 | 首次运行向导配置，存 `~/.choreo/config.json` |
| HITL 确认 | 智能分级 | 普通操作内联简洁；危险操作（rm/force push/drop）红色警告框 |
| 初始化 | 交互式向导 | 首次 `choreo` 时自动运行，存配置后不再显示 |

---

## 视觉规格

### 顶部状态栏

```
◉ Choreo  feat/chat-platform-integration · deepseek-chat
```

- `◉ Choreo` — 主题色（用户配置）
- 分支名 — chalk.green
- 模型名 — chalk.blue
- 分隔符 `·` — chalk.gray

### 对话区

```
❯ 帮我做个 git commit                    ← chalk.white，提示符主题色

💭 已思考 4 步 ▶                         ← 灰色折叠行，回车展开

我来帮你创建 git commit。                 ← AI 回答，chalk.white 流式输出
```

思考块展开后：
```
💭 已思考 4 步 ▼
  ╎ 分析暂存区变更...
  ╎ backend/choreo/auth/deps.py 已修改
  ╎ 选择 commit 类型：feat
  ╎ 生成 message...
```

### HITL — 普通操作

```
┌─ bash ──────────────────────────────────────────────────┐
│ git add -A && git commit -m "feat(auth): bypass"        │
└─────────────────────────────────────────────────────────┘
[y] 执行  [n] 拒绝  [e] 编辑  [!] 之后全部允许
❯ _
```

### HITL — 危险操作（含 rm / force push / DROP TABLE 等）

```
⚠ bash                                  [危险操作]
  rm -rf ./logs/*.log
─────────────────────────────────────────
[y] 确认删除  [n] 拒绝  [e] 编辑命令
❯ _
```

危险操作判断规则：命令包含 `rm -rf` / `git push --force` / `DROP` / `truncate` / `delete` 时自动升级为红色框。

### Skill Suggestion Banner

```
╭──────────────────────────────────────────────────────────╮
│ 💡 建议保存为技能：git-workflow/auto-commit               │
│    多步 git 流程，每次可复用                               │
│    [y] 保存  [n] 忽略                                     │
╰──────────────────────────────────────────────────────────╯
```

---

## 首次运行向导

```
$ choreo

👋 欢迎使用 Choreo CLI！先做个简单配置。

? 后端 API 地址 (默认 http://localhost:8000): _

? 选择主题色:
  ❯ Indigo 紫  (#6366f1)
    Emerald 绿 (#10b981)
    Sky 蓝     (#0ea5e9)
    Rose 玫红  (#f43f5e)
    Amber 琥珀 (#f59e0b)
    自定义...

✓ 配置已保存到 ~/.choreo/config.json

🎼 开始对话吧！输入 /help 查看可用命令。

❯ _
```

---

## 斜杠命令

| 命令 | 功能 |
|------|------|
| `/new` | 创建新线程 |
| `/thread <id>` | 切换到指定线程 |
| `/model <name>` | 切换模型 |
| `/config` | 重新运行配置向导 |
| `/help` | 显示帮助 |
| `/quit` | 退出（Ctrl+C 同效） |

---

## 技术架构

```
cli/
├── src/
│   ├── index.ts          ← commander 入口
│   ├── config.ts         ← 读写 ~/.choreo/config.json
│   ├── wizard.ts         ← 首次运行向导（inquirer）
│   ├── client.ts         ← 后端 REST API 封装
│   ├── stream.ts         ← @langchain/langgraph-sdk SSE 消费
│   ├── renderer.ts       ← 终端渲染（chalk）
│   ├── hitl.ts           ← HITL 分级确认交互
│   ├── theme.ts          ← 主题色工具函数
│   └── commands/
│       ├── chat.ts       ← 交互 REPL
│       └── run.ts        ← 单次运行
├── package.json
└── tsconfig.json
```

### 依赖

| 包 | 用途 |
|----|------|
| `commander` | CLI 参数解析 |
| `chalk` | 终端颜色 |
| `ora` | spinner |
| `inquirer` | 向导交互（首次运行） |
| `@langchain/langgraph-sdk` | SSE 流（与前端共用） |
| `tsx` | 直接运行 TS（开发） |
| `tsup` | 打包发布 |

---

## 与后端集成

- 无需修改后端，直接连接 `http://localhost:8000`（可配置）
- 后端已设置 `auth_mode: all`，无需 Token
- Node.js 无浏览器 CORS 限制，直接 fetch 即可
- SSE 格式与前端 `useChat.ts` 完全一致，复用同一 SDK

---

## 验收标准

1. `cd cli && npm install && npx tsx src/index.ts` → 显示向导（首次）或 REPL
2. 输入问题 → 流式输出，思考块折叠显示
3. 触发工具调用 → 内联确认框 → `y` 执行
4. 触发 `rm -rf` → 红色警告框
5. 思考块按回车展开/折叠
6. `choreo run "列出当前目录"` → 输出后自动退出
7. `/config` → 重新进入主题/API 配置向导
8. `CHOREO_API_URL=http://other:8000 choreo` → 连接指定后端
