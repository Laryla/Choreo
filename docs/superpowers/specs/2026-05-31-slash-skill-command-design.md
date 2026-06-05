# Slash Skill Command Design

**Date:** 2026-05-31
**Goal:** 让用户在聊天输入框中通过 `/category/name` 斜杠命令直接触发技能，将技能内容展开为消息发送给 agent，对标 Claude Code 的自定义斜杠命令机制。

---

## 背景

Choreo 已有完整的技能库（`LocalSkillStore`、`SKILL.md`），agent 可以主动 `skill_view` 查阅技能。但用户没有直接触发特定技能的入口——必须描述任务后等 agent 自行决定调用哪个技能，或依赖 `SkillsContextMiddleware` 的自动注入。

本设计补齐"用户主动指定技能"的入口，模仿 Claude Code 的斜杠命令交互模型：

- Claude Code：`.claude/commands/skill.md` + `/skill-name $ARGUMENTS` → 展开为 prompt 发送给 Claude
- Choreo：`skills/category/name/SKILL.md` + `/category/name $ARGUMENTS` → 展开为消息发送给 agent

---

## 架构概览

**前端为主，后端改动极小（仅新增一个只读字段用于弹窗提示，不影响核心功能）。**

```
用户输入 "/"
  → ChatInput 检测触发符（输入内容以 "/" 开头）
  → 读取 SWR 缓存的技能列表（已有 /api/skills/ 请求）
  → 渲染技能选择弹窗，支持继续输入过滤
  → 用户选中技能（键盘 ↑↓ Enter 或鼠标点击）
  → 输入框进入「命令模式」，显示 "/git/weekly-report "
  → 用户输入参数（如 "本周"）
  → 按 Enter 发送
  → 前端 fetch GET /api/skills/git/weekly-report 拿到技能全文
  → $ARGUMENTS 替换为 "本周"
  → 展开后的完整文本作为普通消息发送
```

agent 收到的是展开后的 prompt，不感知斜杠命令的存在。

---

## 第一部分：触发与弹窗

### 触发条件

输入框内容**以 `/` 开头**（不是任意位置的 `/`，只有行首）。

### 弹窗行为

| 用户输入 | 弹窗内容 |
|---------|---------|
| `/` | 所有 active 技能，pinned 优先 |
| `/git` | category 含 "git" 或 name/description 含 "git" 的技能 |
| `/git/week` | `git/weekly-report` 等精确匹配 |
| `/xyz`（无匹配）| 弹窗关闭，回到普通输入模式 |

### 弹窗每行显示

```
git/weekly-report    根据 git log 生成飞书周报
                     参数：时间范围，例如"本周"
```

- 第一行：`skill_id`（加粗）+ `description`
- 第二行（可选）：`arguments` 字段内容，灰色小字，告诉用户该输入什么参数

### 键盘交互

| 按键 | 行为 |
|-----|------|
| ↑ / ↓ | 在弹窗列表中导航 |
| Enter | 选中高亮项 |
| Escape | 关闭弹窗，保留已输入文字 |
| Tab | 同 Enter（选中） |

### 弹窗定位

弹窗显示在输入框上方（`bottom: 100%`），最多显示 6 条，超出可滚动。

---

## 第二部分：命令模式

用户选中技能后，输入框进入命令模式：

**输入框内容：** `/git/weekly-report ` （命令名 + 空格，光标在末尾）

**视觉提示：** 发送按钮左侧显示技能名小标签：
```
[git/weekly-report ×]  [↑]
```
点击 `×` 清除命令，退出命令模式，保留 `$ARGUMENTS` 部分文字。

**退出命令模式：**
- 点击技能标签上的 `×`
- 手动删除输入框开头的 `/category/name` 部分

---

## 第三部分：展开逻辑

发送时，`handleSend` 检测是否处于命令模式，若是则展开后再发送：

```typescript
async function expandSlashCommand(text: string): Promise<string> {
  const match = text.match(/^\/([a-z0-9_-]+\/[a-z0-9_-]+)(?:\s+([\s\S]*))?$/)
  if (!match) return text

  const [, skillId, args = ""] = match
  const [category, name] = skillId.split("/")

  // 从 API 拉取技能全文（带 SWR 缓存）
  const res = await fetch(`${API}/api/skills/${category}/${name}`)
  if (!res.ok) return text  // 技能不存在，原样发送
  const skill = await res.json()

  const content: string = skill.content ?? ""
  const trimmedArgs = args.trim()

  if (content.includes("$ARGUMENTS")) {
    return content.replace(/\$ARGUMENTS/g, trimmedArgs)
  }
  // 无 $ARGUMENTS：有参数则追加，无参数原样
  return trimmedArgs ? `${content}\n\n${trimmedArgs}` : content
}
```

**展开规则汇总：**

| 技能内容 | 用户参数 | 发送内容 |
|---------|---------|---------|
| 含 `$ARGUMENTS` | "本周" | 内容中 `$ARGUMENTS` → "本周" |
| 含 `$ARGUMENTS` | （空） | 内容中 `$ARGUMENTS` → "" |
| 不含 `$ARGUMENTS` | "本周" | 技能内容 + `\n\n本周` |
| 不含 `$ARGUMENTS` | （空） | 技能内容原样 |
| 技能不存在 | 任意 | 原始输入文字原样发送 |

---

## 第四部分：SKILL.md 格式扩展

不改现有格式，仅增加一个**可选** frontmatter 字段 `arguments`：

```yaml
---
name: 周报生成
description: 根据 git log 生成飞书周报
arguments: "时间范围，例如：本周 / 2026-05-01 到 2026-05-07"
---

帮我整理 git commit，生成一份周报。
时间范围：$ARGUMENTS
格式：飞书 Markdown
```

- `arguments`：字符串，显示在弹窗中作为参数说明，不影响展开逻辑
- 旧技能不加此字段也完全兼容，弹窗中不显示参数提示行

**后端 `Skill` 模型**需新增 `arguments: str | None = None`，从 frontmatter 解析，只读不写。

---

## 第五部分：文件改动范围

| 文件 | 改动 |
|------|------|
| `frontend/src/components/Chat/ChatInput.tsx` | 核心：斜杠检测、弹窗、命令模式、展开逻辑 |
| `frontend/src/api/skills.ts` | 新增 `arguments?: string` 字段到 `Skill` 接口 |
| `backend/choreo/models/skill.py` | `Skill` 新增 `arguments: str \| None = None` |
| `backend/choreo/skills/store.py` | `_parse_dir` 从 frontmatter 读取 `arguments` |
| `backend/tests/test_skill_store.py` | 新增 arguments 解析测试 |

前端无新文件，后端无新路由，改动范围极小。

---

## 不在本次范围内

- 斜杠命令历史记录（最近使用）
- 用户自定义快捷命令别名（`/wr` → `/git/weekly-report`）
- 弹窗内技能预览（点击展开查看 SKILL.md 全文）
- 多 `$ARGUMENTS` 占位（`$ARGUMENTS_1`、`$ARGUMENTS_2`）
