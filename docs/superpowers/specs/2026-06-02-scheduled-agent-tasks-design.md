# Scheduled Agent Tasks — Design Spec

**Date:** 2026-06-02  
**Status:** Draft  
**Branch:** feat/chat-platform-integration

---

## 背景与目标

用户有一批需要定期自动执行的信息收集任务（GitHub 热门项目追踪、LangChain 版本更新监控、周报生成等），这些任务需要 Agent 能够主动运行、收集结果、并通知用户。

目前 Choreo 已有任务 CRUD 接口和数据库 schema，但缺少：
- 调度引擎（cron 触发）
- Agent 执行层（无人值守运行）
- 运行历史存储
- 通知渠道（飞书）
- 前端结果展示页

本设计实现"独立任务运行器"方案，将定时任务与聊天线程完全分离。

---

## 架构概览

```
APScheduler (cron 触发)
    └── TaskRunner.run(task_id)
            ├── 创建 TaskRun 记录 (status=running)
            ├── 初始化 Task Agent (web_search + http_fetch 工具)
            ├── 执行 Agent，流式收集输出
            ├── 更新 TaskRun (status=success, output=markdown)
            └── NotifierRouter.send(task, run)
                    └── FeishuNotifier → POST webhook

用户创建任务
    ├── Chat: Choreo Agent 调用 create_task 工具 → POST /api/tasks
    └── UI 表单: CreateTaskModal → POST /api/tasks

用户查看结果
    └── /tasks/:taskId → TaskRunsPage
            ├── 运行历史列表 (GET /api/tasks/:id/runs)
            └── 点击展开完整 Markdown 输出
```

---

## 数据模型

### 更新 `TaskRow`（现有表添加字段）

| 新字段 | 类型 | 说明 |
|--------|------|------|
| `prompt` | text | Agent 执行指令（任务的核心，如"搜索本周 GitHub Stars 增长最快的项目"） |
| `notify_config` | JSON | 通知配置，如 `{"type": "feishu", "webhook": "https://..."}` |

### 新表 `task_runs`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | UUID，主键 |
| `task_id` | string | FK → tasks.id，索引 |
| `status` | string | `pending` / `running` / `success` / `failed` |
| `started_at` | bigint | Unix 时间戳（毫秒） |
| `finished_at` | bigint | nullable |
| `output` | text | Agent 生成的 Markdown 内容 |
| `error` | text | nullable，失败原因 |

---

## 后端模块

### `choreo/scheduler/`（新建）

```
choreo/scheduler/
├── engine.py       # APScheduler 初始化；在 app.py lifespan 中 start/shutdown
├── runner.py       # TaskRunner.run(task_id)：创建 run 记录 → 执行 agent → 更新结果
└── notifiers/
    ├── base.py     # BaseNotifier ABC: async def send(task, run) -> None
    └── feishu.py   # FeishuNotifier：POST webhook，body 含任务名+摘要+结果链接
```

**engine.py 关键逻辑：**
- `AsyncIOScheduler` 启动时从数据库加载所有 `status=active` 的任务，按 `cron` 注册 job
- CRUD 操作（创建/暂停/删除）同步更新 scheduler 中的 job

**runner.py 关键逻辑：**
- 创建 `task_runs` 记录，status=running
- 调用 `create_choreo_agent(headless=True)` 获取无人值守模式的主 Agent
- `ainvoke({"messages": [HumanMessage(content=task.prompt)]})`
- 提取输出写入 `output`，更新 status=success/failed

### `choreo/agents/tools/task_tool.py`（新建）

为 Choreo 主 Agent 提供两个 LLM 工具：

```python
@tool
async def create_task(name: str, description: str, cron: str, prompt: str, webhook: str = "") -> str:
    """创建一个定时 Agent 任务"""

@tool  
async def list_tasks() -> str:
    """列出当前所有定时任务"""
```

这两个工具注册到 `create_choreo_agent(tools=[..., create_task, list_tasks])`。

### API 新增端点（`routers/tasks.py` 扩展）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tasks/{tid}/runs` | 列出运行历史（分页，默认最近 20 条） |
| GET | `/api/tasks/{tid}/runs/{rid}` | 获取单次运行详情（含完整 output） |
| POST | `/api/tasks/{tid}/runs` | 手动立即触发一次 |

### `TaskCreate` 模型更新

新增字段：`prompt: str`、`notify_config: dict = {}`

---

## 前端模块

### 新页面 `TaskRunsPage`（`/tasks/:taskId`）

- 展示任务名称、cron、状态
- 运行历史列表：时间、状态 badge、输出摘要（前 100 字）
- 点击展开面板：完整 Markdown 渲染（复用 `ChatMessage` 的渲染逻辑）
- "立即触发"按钮 → POST `/api/tasks/:id/runs`

### 更新 `TaskListPage`

- 任务卡片新增：`last_run` 时间、运行状态
- "任务名称"可点击 → 跳转 `/tasks/:taskId`
- "+ 新建任务"按钮打开 `CreateTaskModal`

### 新组件 `CreateTaskModal`

表单字段：
- 任务名称（必填）
- 描述（可选）
- Cron 表达式（必填，提供常用预设下拉：每天、每周一、每小时）
- Agent 指令 prompt（必填，textarea，如"搜索本周 GitHub Stars 增长最快的 10 个项目，按增量排序，给出简短描述"）
- 飞书 Webhook URL（可选）

---

## 通知格式（飞书）

```json
{
  "msg_type": "interactive",
  "card": {
    "header": { "title": { "content": "✅ 任务完成：{task.name}" } },
    "elements": [
      { "tag": "markdown", "content": "{output 前 500 字}..." },
      { "tag": "action", "actions": [{ "tag": "button", "text": "查看完整结果", "url": "{app_url}/tasks/{task_id}" }] }
    ]
  }
}
```

---

## 集成点

### `gateway/app.py` lifespan

```python
scheduler = TaskScheduler()
await scheduler.start()          # 加载所有 active 任务
yield
await scheduler.shutdown()
```

### `agents/choreo_agent.py`

`create_choreo_agent` 新增 `headless: bool = False` 参数，控制 middleware 组合：

```python
def create_choreo_agent(checkpointer=None, headless=False):
    middlewares = [
        ModelSelectorMiddleware(),
        ModelCallLimitMiddleware(),
    ]
    if not headless:
        middlewares.append(HumanInTheLoopMiddleware(...))  # 聊天模式：需要人工审批
        middlewares.append(TitleMiddleware())               # 聊天模式：自动生成标题
    
    return create_agent(
        model=load_model(),
        tools=[all_tools..., create_task, list_tasks],  # 工具全量保留，含任务管理工具
        middleware=middlewares,
        checkpointer=checkpointer if not headless else None,
    )

# 聊天模式（现有）
agent = create_choreo_agent(checkpointer=checkpointer)

# 任务执行模式（headless）：全部工具可用，去掉 HITL / Title / Checkpointer
agent = create_choreo_agent(headless=True)
```

**headless 模式下保留的能力：**
- 所有工具（git、script、runner、notify、web_search 等）
- ModelSelectorMiddleware（可按任务配置指定模型）
- ModelCallLimitMiddleware（防止失控循环）

**headless 模式下去掉的：**
- `HumanInTheLoopMiddleware` — 无人值守，HITL 会永久卡住
- `TitleMiddleware` — 任务无需生成对话标题
- `checkpointer` — 任务无需断点续跑

---

## 验证方式

1. **调度引擎**：创建一个 cron=`* * * * *`（每分钟）的测试任务，确认 `task_runs` 每分钟新增一条记录
2. **Agent 执行**：手动触发 GitHub 热门项目任务，检查 `output` 字段包含有效 Markdown
3. **飞书通知**：配置 webhook，触发任务后确认飞书收到卡片消息
4. **LLM 工具创建任务**：在聊天中说"帮我每周一早上8点追踪 LangChain 更新"，确认任务被创建
5. **前端结果页**：访问 `/tasks/:id`，确认运行历史列表正常，Markdown 渲染正确

---

## 扩展设计

### 2. 任务运行时可见性（流式写入）

默认 `ainvoke` 要等 Agent 完全结束才有结果，长任务用户体验差。改为流式追加：

- `runner.py` 改用 `astream`，每收到一个 chunk 就 `UPDATE task_runs SET output = output || chunk`
- 前端 `TaskRunsPage` 对 `status=running` 的任务每 3 秒轮询一次，实时展示增量输出
- 任务完成后停止轮询，切换为静态展示

### 3. Headless 模式工具白名单

去掉 HITL 后，Agent 可以无审批执行 `bash`、`git push` 等危险操作。需明确两种策略（在 `config.yaml` 中配置）：

```yaml
scheduler:
  tool_policy: whitelist   # whitelist（只允许列出的工具）或 all（全放行）
  allowed_tools:
    - web_search
    - http_fetch
    - read_file
    - list_dir
```

`runner.py` 根据 `tool_policy` 过滤传给 `create_choreo_agent(headless=True, tools=allowed_tools)` 的工具列表。默认策略为 `whitelist`，需显式配置才能开放写操作类工具。

### 4. 跨次运行上下文

同一任务的多次运行结果可互相感知，支持"对比分析"场景（如"本周 vs 上周 GitHub 热门变化"）。

实现方式：`runner.py` 在构造 Agent prompt 时，自动拼入上一次成功运行的 `output`：

```python
last_run = await get_last_successful_run(task_id)
context = f"\n\n---\n上次运行结果（{last_run.finished_at}）：\n{last_run.output}" if last_run else ""
full_prompt = task.prompt + context
```

`task_runs` 表无需变更，复用已有 `output` 字段。任务 prompt 中可用占位语言描述预期行为，如"与上次结果对比，指出新增和消失的项目"。

### 6. 通知渠道扩展

`BaseNotifier` 已是 ABC，扩展只需两步：

1. 在 `notifiers/` 下新建文件实现 `BaseNotifier.send(task, run)`
2. 在 `NotifierRouter` 的 `NOTIFIERS` dict 加一行

`notify_config.type` 当前支持的取值：

| type | 实现文件 | 必填字段 |
|------|---------|---------|
| `feishu` | `notifiers/feishu.py` | `webhook` |
| `email` | `notifiers/email.py`（待实现） | `to`, `smtp_*` |
| `wecom` | `notifiers/wecom.py`（待实现） | `webhook` |
| `slack` | `notifiers/slack.py`（待实现） | `webhook` |

通知配置存在 `task.notify_config` JSON 字段中，支持配置多个渠道：

```json
{
  "channels": [
    {"type": "feishu", "webhook": "https://..."},
    {"type": "email", "to": "me@example.com"}
  ]
}
```

---

## 不在本期范围内

- 周报数据源（git commits / chat 记录读取）
- 任务间依赖（A 完成后触发 B）
- 任务执行超时重试策略
- 多用户隔离的通知配置
- 任务模板库
