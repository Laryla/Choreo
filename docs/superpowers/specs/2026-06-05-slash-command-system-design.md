# Choreo CLI 斜杠命令系统设计

## 概述

为 Choreo CLI 添加 Claude Code 风格的斜杠命令选择器：输入 `/` 后展开带分组的命令列表，支持实时过滤和 Tab 补全。同时新增 5 条内置命令（`/model`、`/clear`、`/compact`、`/history`、`/status`），架构上为未来用户自定义命令保留扩展口。

---

## 设计决策

| 维度 | 决定 | 说明 |
|------|------|------|
| 命令来源 | 内置命令（暂不支持用户自定义） | 架构上留扩展口，未来可从 `.choreo/commands/` 加载 |
| 触发方式 | 输入 `/` 后打印静态列表 | 无需 raw terminal mode，简单可靠 |
| 过滤方式 | 继续输入字母实时过滤 | readline 行级处理，无需 inquirer |
| 列表内容 | 命令名 + 简短描述 + 分组 | 与 Claude Code 风格一致 |

---

## 命令集

### 已有命令（保留）

| 命令 | 功能 |
|------|------|
| `/new` | 新建对话（重置 threadId） |
| `/thread <id>` | 切换到指定线程 |
| `/config` | 重新运行配置向导 |
| `/help` | 打印命令列表（复用命令选择器样式） |
| `/quit` | 退出（Ctrl+C 同效） |

### 新增命令

| 命令 | 功能 |
|------|------|
| `/model [name]` | 无参数：列出可用模型并选择；有参数：直接切换 |
| `/clear` | 清屏（`\x1b[2J\x1b[H`），保留当前线程 |
| `/compact` | 发指令给 AI 压缩上下文，返回摘要后继续对话 |
| `/history` | 列出最近线程（标题 + ID），选择后切换 |
| `/status` | 显示后端连接状态、线程 ID、当前模型、git 分支 |

---

## 命令选择器 UI

### 触发与展示

```
❯ /                        ← 用户输入 /
  对话
    /new
    /clear
    /compact
  线程
    /thread <id>
    /history
  模型 & 配置
    /model [name]
    /config
  系统
    /status
    /help
    /quit

  Tab 补全 · Enter 确认 · Esc 取消
```

### 过滤

```
❯ /m                       ← 继续输入
  匹配: /model              ← 只显示匹配项（灰色显示不匹配项）
  
  Tab 或 Enter 补全
```

- 过滤忽略大小写，前缀匹配
- 唯一匹配时 Enter 直接执行
- 输入 `Esc` 或退格清空回到正常输入

---

## 各命令执行效果

### `/model`（无参数）

```
❯ /model
  ● deepseek-chat       ← 当前模型（绿点标注）
    deepseek-reasoner
    claude-sonnet-4-6

  Enter 切换到选中模型
```

输入 `/model deepseek-reasoner` 直接切换，无需二次选择。切换后状态栏模型名同步更新。

### `/status`

```
❯ /status
  后端    ● 已连接
  地址    localhost:8000
  线程    abc-1234-…
  模型    deepseek-chat
  分支    feat/chat-platform-integration
```

后端不可达时 `● 已连接` 变为红色 `✗ 无法连接`。

### `/compact`

```
❯ /compact
  压缩对话上下文...
  ✓ 已压缩至摘要（32 → 4 条消息）
  上下文已精简，继续对话不影响记忆
```

实现：向 AI 发送系统级 compact prompt，AI 返回摘要后用摘要替换当前线程的消息历史（通过 POST `/threads/{tid}/state`）。

### `/history`

```
❯ /history
  ● abc-1234    feat: CLI 设计         ← 当前线程（绿点）
    def-5678    auth bypass
    ghi-9012    sandbox impl

  Enter 切换 · 最近 10 条
```

最多显示最近 10 条线程（GET `/threads/` 取前 10）。

### `/clear`

清屏（ANSI `\x1b[2J\x1b[H`），重新打印状态栏，线程 ID 保留。

---

## 技术架构

### 新增文件

```
cli/src/
└── commands.ts     ← 命令注册表 + 命令选择器逻辑
```

### 命令注册表结构

```ts
interface CommandDef {
  name: string;           // e.g. "new"
  args?: string;          // e.g. "<id>" or "[name]"
  description: string;
  group: 'conversation' | 'thread' | 'model' | 'system';
  run: (args: string, ctx: CommandContext) => Promise<void>;
}

interface CommandContext {
  config: ChoreoConfig;
  client: ApiClient;
  renderer: Renderer;
  theme: Theme;
  getThreadId: () => string | null;
  setThreadId: (id: string | null) => void;
  getCurrentModel: () => string;
  setCurrentModel: (name: string) => void;
  readline: readline.Interface;
}
```

所有命令通过 `registerCommand(def: CommandDef)` 注册，`chat.ts` 启动时统一注册全部命令。

### 命令选择器逻辑（`handleSlashInput`）

```ts
async function handleSlashInput(
  partial: string,           // 用户已输入内容（含 /）
  ctx: CommandContext,
): Promise<'continue' | 'executed' | 'cancelled'>
```

1. `partial === '/'` → 打印完整分组列表，等待下一行输入
2. `partial` 有后续字符 → 过滤匹配命令并打印
3. 精确匹配一条 → 解析参数并调用 `run()`
4. `Esc` 或空行 → 返回 `'cancelled'`

### chat.ts 集成

`chat.ts` 的 `askUser()` 返回后：

```ts
if (trimmed.startsWith('/')) {
  const result = await handleSlashInput(trimmed, ctx);
  if (result !== 'executed') continue;
  // executed 时命令内部已处理，无需额外操作
} else {
  // 正常消息流
}
```

---

## 扩展口（未来自定义命令）

`commands.ts` 导出 `registerCommand`，未来加载自定义命令只需：

```ts
// 未来实现：扫描 .choreo/commands/*.md
const customCmds = await loadCustomCommands(config);
customCmds.forEach(registerCommand);
```

内置命令和自定义命令共用同一套选择器 UI，无需修改选择器逻辑。

---

## 验收标准

1. 输入 `/` 后打印分组命令列表
2. 输入 `/m` 过滤后只显示 `/model`，Enter 执行
3. `/model` 无参数列出可用模型，Enter 切换，状态栏同步更新
4. `/status` 正确显示后端状态、线程、模型、分支
5. `/compact` 发送压缩指令，返回摘要行
6. `/history` 列出最近 10 条线程，选择后切换
7. `/clear` 清屏后状态栏重新渲染，线程 ID 保留
8. `/help` 复用命令选择器样式输出
9. 所有已有命令（`/new`、`/thread`、`/config`、`/quit`）行为不变
