# Skill Self-Evolution Design

**Date:** 2026-05-31  
**Goal:** 让 Choreo agent 越用越聪明——每轮对话后自动复盘，将有价值的知识沉淀为技能，持续提升 agent 在当前用户环境和工作方式下的效能。

---

## 背景

Choreo 已有完整的技能基础设施（`LocalSkillStore`、`SKILL.md` 格式、`SkillsContextMiddleware`、`skill_view` 工具），但 agent 目前只能读技能，不能写技能，也没有复盘机制。本设计补齐这两块，使技能库随使用自动进化。

参照：[Hermes Agent](https://github.com/NousResearch/hermes-agent) 的 `background_review.py` 架构。

---

## 架构概览

```
用户对话（SSE 流）
    │
    ├─ 对话中 ──► 主 agent 持有 skill_view / skill_patch / skill_create
    │              ├─ 用户说"记下这个" → 立即调用 skill_patch/create，实时反馈
    │              └─ agent 主动判断有复用价值 → 任务完成后调用（不打断中途流程）
    │
    └─ finally 块 ──► 提取 invoked_skills（本次 skill_view 调用列表）
                  └─► asyncio.create_task(background_review(thread_id, messages, invoked_skills))
                            │
                            ├─ 加载 review_model（config.yaml）
                            ├─ 构造受限 agent（skill_view / skill_patch / skill_create）
                            ├─ 注入复盘 system prompt
                            │     + 完整对话历史
                            │     + invoked_skills 列表（已知调用的技能 ID）
                            ├─ agent 运行 → 捕获隐性信息，补漏主 agent 未记录的内容
                            └─ 滚动写 .review_log.jsonl（保留最近 100 条）

前端（仅当复盘任务启动时，设置 15s 延迟刷新）
    └─ mutate(SKILLS_KEY) → 技能面板刷新
                          → AI 更新标记 / 摘要展示
```

---

## 第一部分：Agent 工具层

### 新增工具

#### `skill_patch(skill_id, content?, description?, tags?)`

更新已有技能的内容或元数据。

**写入前检查（任一条件成立则拒绝）：**
- `source == "builtin"`：内置技能，只读
- `locked == true`：用户锁定，只读
- 新 content 超过 15KB：超出大小限制，拒绝写入

**写入行为：**
- 只更新传入的字段，未传入的字段保持原值
- 自动 bump `patch_count` 和 `last_activity_at`
- `source` 字段保持原值不变（用户手写的技能 patch 后仍是 `"manual"`）
- 在 `.usage.json` 写入 `last_reviewed_at`（时间戳）和 `last_reviewed_by`（thread_id）

**返回：** 更新后的技能摘要，或拒绝原因（"内置技能不可修改" / "技能已被用户锁定" / "内容超过 15KB 限制，请精简后重试"）

#### `skill_create(category, name, description, content, tags?)`

新建技能。

**写入前检查：**
- 若 `category/name` 已存在 → 返回错误，提示改用 `skill_patch`
- content 超过 15KB → 拒绝，提示精简

**重名检测（工具层辅助）：** 工具返回同 category 下所有现有技能的 `id + description` 列表，要求 agent 确认没有语义重复后再调用。agent 应先 `skill_view` 相近技能对比，再决定是 patch 还是新建。

**写入行为：**
- `source` 固定为 `"ai_review"`
- `locked` 默认 `false`
- 写入 `.usage.json`，记录 `last_activity_at`、`last_reviewed_at`、`last_reviewed_by`（thread_id）

**返回：** 新建技能的 skill_id + 同 category 现有技能列表（供 agent 二次确认），或冲突错误。

### 主 Agent 也可调用写工具

`skill_patch` 和 `skill_create` 同时挂到**主对话 agent** 的工具集（不只是复盘 agent）。

工具描述中加约束，控制触发时机：

```
仅在以下情况调用：
1. 用户明确要求记录某个方法、偏好或约定
   （如"把这个记成技能"、"记住我喜欢这种格式"）
2. 你确信刚发现的内容对未来同类任务有高复用价值，
   且任务已完成、不会打断当前流程

不要在任务进行中途中断去写技能——后台复盘会在对话结束后处理。
```

**两种模式的分工：**

| | 主 Agent 写技能 | 背景复盘写技能 |
|---|---|---|
| 触发 | 用户指令 / agent 主动判断 | 自动，对话结束后 |
| 时机 | 实时，对话中 | 延迟，流结束后 |
| 质量 | 用户直接参与，意图明确 | 全局视角，覆盖隐性信息 |
| 风险 | agent 可能打断对话节奏 | 质量依赖 prompt 和 model |

两者互补：主 agent 处理显式需求，复盘负责兜底捕获隐性信息。

### 保护标记扩展

在 `.usage.json` 每个条目新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `locked` | bool | 写保护，agent 不可修改（默认 false） |
| `last_reviewed_at` | int \| null | 最近一次 AI 复盘时间戳 |
| `last_reviewed_by` | str \| null | 触发此次复盘的 thread_id |

- `pinned`：UI 置顶（已有，不变）
- `locked`：写保护（新增）—— agent 不可修改，用户可在技能面板切换

前端技能卡片新增锁图标（🔒），点击切换 locked 状态，调用 `PATCH /skills/{skill_id}`。

---

## 第二部分：背景复盘 Worker

### 配置

```yaml
# config.yaml 新增字段
review_model: deepseek-chat   # 不填则复用 active_model
```

### 触发与并发控制

`runs.py` SSE 流的 `finally` 块：

```python
# 从 LangGraph state 提取本次 skill_view 调用列表
invoked_skills = extract_invoked_skills(messages)  # 解析 tool call 记录

review_started = await maybe_start_review(
    thread_id=tid,
    messages=messages_snapshot,
    invoked_skills=invoked_skills,
)
```

**并发策略（改进版）：**
- 每个 `thread_id` 维护一个锁 + 一个 `pending_snapshot` 槽
- 若当前有复盘在运行：将最新 messages 存入 `pending_snapshot`（覆盖旧的）
- 当前复盘完成后：若 `pending_snapshot` 非空，自动用最新快照补跑一次
- 这样无论用户发多少轮消息，最后一次的信息都不会丢失

**`invoked_skills` 提取：** 遍历 messages 中所有 `tool_use` 类型节点，筛选 `name == "skill_view"` 的调用，收集其 `skill_id` 参数。这是确定性提取，不依赖 agent 推断。

**仅当 `review_started == True` 时，前端才设置 15s 延迟刷新。**

### 受限 Agent 工具集

| 工具 | 用途 |
|------|------|
| `skill_view` | 读取现有技能全文，判断是否需要 patch |
| `skill_patch` | 更新技能内容（含大小检查） |
| `skill_create` | 新建技能（含同 category 已有技能提示） |

不赋予：bash、git、mcp、file_tools 等工具。

### 复盘 System Prompt

注入到复盘 agent 的 system message，对话历史作为 user message 传入：

```
你是 Choreo 的技能复盘 agent。你的核心使命是：
让 agent 在这个用户的环境和工作方式下越来越有效。

## 本次已知信息

本次对话中 agent 主动查阅了以下技能（已确认调用）：
{invoked_skills_list}  ← 运行时填入，如 ["git/weekly-report", "python/asyncio"]

这些技能是优先 patch 的候选。用 skill_view 读取全文后再决定是否修改。

## 三类值得记录的信息

**1. 用户的工作方式和偏好**
- 用户偏好的代码风格、提交格式、命名习惯
- 用户喜欢怎样的解释方式（详细/简洁、中文/英文）
- 用户在这个项目里遵循的约定

**2. 这个场景下有效的方法**
- 解决某类问题时哪个路径更短
- 哪些工具组合在这个项目里效果好
- agent 走了弯路后发现的更优做法

**3. 避坑信息**
- 在这个环境里踩过的坑（依赖冲突、路径问题、API 怪癖）
- 用户明确说"不要这样做"的模式
- 上一次做错的地方，这次做对了的原因

## 写入优先级（按顺序尝试）

1. patch 上方列出的已调用技能（先 skill_view 读全文，再决定改哪里）
2. patch 其他相关现有技能（需先 skill_view 确认内容再 patch）
3. 新建技能（仅当没有任何现有技能覆盖这个场景时）
   - 新建前：查看 skill_create 返回的同 category 现有列表，确认无语义重复

## 写入质量要求

- 记录的是"下次遇到类似情况，agent 应该怎么做"，而不是"这次发生了什么"
- patch 时只追加或修正，不整体重写，单次 patch 后技能总大小不超过 15KB
- 新建技能的 description 必须一句话回答"何时用这个技能"
- category 用小写英文，name 用 kebab-case，tags ≤ 3 个

## 明确不写的情况

- 内置技能（source=builtin）— 工具会拒绝
- 被锁定的技能（locked=true）— 工具会拒绝
- 纯环境错误（缺包、权限、网络）— 不是可复用的知识
- 完全一次性的任务，未来不可能遇到相同场景
- 对话内容过于简单或无实质内容（如纯问候）— 直接退出即可，无需强行写
```

### 复盘结果日志

复盘完成后滚动写入 `{skills_dir}/.review_log.jsonl`：

```json
{"thread_id": "xxx", "ts": 1748650000, "updated": ["git/weekly-report"], "created": ["python/asyncio-debug"]}
```

**滚动策略：** 文件超过 100 条时，写入新条目的同时删除最旧一条（保持文件最多 100 行）。`GET /skills/review_log` 路由读取最后 N 条返回，不扫全文。

---

## 第三部分：前端结果展示

### 刷新时机

`useChat.ts` 的 `sendMessage` 调用后，**仅当后端返回"复盘已启动"信号时**才设置延迟刷新：

```ts
// SSE 流结束后，后端在最后一个 event 里附带 review_started: bool
if (reviewStarted) {
  mutate(SKILLS_KEY)                                  // 立即刷（use_count 等）
  setTimeout(() => mutate(SKILLS_KEY), 15_000)       // 15s 后再刷，覆盖复盘完成
  // revalidateOnFocus 是兜底，复盘超过 15s 时下次聚焦窗口自动刷
}
```

**如何传递 `review_started` 信号：** 在 SSE 流的最后一个 `updates` 事件附加 `__review_started: true` 字段，前端解析后设置 setTimeout。

### 技能卡片 AI 更新标记

条件：`last_reviewed_at` 存在且在最近 24 小时内。

展示：技能卡片右上角显示 `✦ AI` 小徽章，hover 显示 tooltip：`AI 于 XX 分钟前更新`。

### 技能面板摘要

读取 `GET /skills/review_log?limit=1`（仅返回最后一条）：

```
上次对话更新了 2 个技能 · 新建了 1 个技能
```

点击展开显示具体技能名称列表，点击技能名跳转到对应技能详情。若本次复盘无更新（updated 和 created 均为空），不显示此摘要。

### 锁定开关

技能卡片操作区新增锁图标：
- 🔓 未锁定（默认）— 点击后调用 `PATCH /skills/{id}` 设置 `locked: true`
- 🔒 已锁定 — 点击后解锁，`locked: false`
- 内置技能（`source === "builtin"`）：锁图标固定显示 🔒 且不可点击

---

## 数据流总览

```
对话结束（SSE finally）
  ↓
提取 invoked_skills（从 tool call 记录确定性解析）
  ↓
maybe_start_review() → 并发控制
  ├─ 无复盘在跑 → 启动新复盘任务，返回 review_started=true
  └─ 有复盘在跑 → 存入 pending_snapshot，返回 review_started=false
                    └─ 当前复盘完成后自动补跑 pending_snapshot

复盘任务运行
  skill_view → 读已调用技能全文
  skill_patch / skill_create → 写技能文件（含大小检查 + 重名检测）
  ↓
滚动写 .review_log.jsonl（≤100 条）
更新 .usage.json（last_reviewed_at + last_reviewed_by）

前端（review_started=true 时）
  立即 mutate(SKILLS_KEY)
  15s 后再次 mutate(SKILLS_KEY)
  → 技能面板刷新，AI 徽章出现
  → GET /skills/review_log?limit=1 → 摘要展示
```

---

## 不在本次范围内

- 离线进化管线（DSPy + GEPA 系统性优化）— 可作为后续独立项目
- 跨 thread 技能效果追踪 / A-B 评估
- 技能版本历史 / 完整 diff 展示
- 复盘完成的实时推送（WebSocket）— `revalidateOnFocus` 已足够
