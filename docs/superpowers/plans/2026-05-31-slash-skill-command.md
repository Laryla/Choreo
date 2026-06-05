# Slash Skill Command Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在聊天输入框实现 `/category/name` 斜杠命令，选中技能后将 SKILL.md 内容展开（替换 `$ARGUMENTS`）作为消息发送给 agent。

**Architecture:** 纯前端展开逻辑，后端仅新增一个只读的 `arguments` 字段用于弹窗参数提示。用户输入 `/` 触发技能选择弹窗，选中后进入命令模式，发送时 fetch 技能全文展开后作为普通消息传给 agent。

**Tech Stack:** React 18 + TypeScript, SWR, Tailwind CSS（前端）；FastAPI + Pydantic（后端）

---

## 文件改动索引

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/choreo/models/skill.py` | Modify | `Skill` 新增 `arguments: str \| None = None` |
| `backend/choreo/skills/store.py` | Modify | `_parse_dir` 从 frontmatter 读取 `arguments` |
| `backend/tests/test_skill_store.py` | Modify | 新增 `arguments` 解析测试 |
| `frontend/src/api/skills.ts` | Modify | `Skill` 接口新增 `arguments?: string` |
| `frontend/src/components/Chat/ChatInput.tsx` | Modify | 斜杠检测、弹窗、命令模式、展开发送 |

---

## Task 1: Backend — `arguments` 字段

**Files:**
- Modify: `backend/choreo/models/skill.py`
- Modify: `backend/choreo/skills/store.py:69-96`
- Modify: `backend/tests/test_skill_store.py`

### 步骤

- [ ] **Step 1: 在测试文件末尾写一个失败测试**

在 `backend/tests/test_skill_store.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_arguments_field_parsed_from_frontmatter(store):
    """arguments 字段从 SKILL.md frontmatter 读取，不写则为 None。"""
    import yaml
    from choreo.skills.store import _DEFAULT_USAGE

    # 手工写一个带 arguments 的 SKILL.md
    skill_dir = store._root / "git" / "weekly-report"
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm = {
        "description": "生成周报",
        "version": "1.0.0",
        "author": "user",
        "tags": [],
        "arguments": "时间范围，例如：本周",
    }
    body = "帮我生成周报，时间范围：$ARGUMENTS"
    text = f"---\n{yaml.dump(fm, allow_unicode=True).rstrip()}\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(text, encoding="utf-8")

    # 写入 usage
    async with store._usage_lock:
        usage = await store._read_usage()
        usage["git/weekly-report"] = {**_DEFAULT_USAGE}
        await store._write_usage(usage)

    skill = await store.get("git/weekly-report")
    assert skill is not None
    assert skill.arguments == "时间范围，例如：本周"


@pytest.mark.asyncio
async def test_arguments_field_none_when_absent(store):
    """arguments 字段不存在时返回 None。"""
    await store.create(SkillCreate(
        category="git", name="log",
        description="Use when reading git history",
    ))
    skill = await store.get("git/log")
    assert skill is not None
    assert skill.arguments is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd backend && uv run pytest tests/test_skill_store.py::test_arguments_field_parsed_from_frontmatter tests/test_skill_store.py::test_arguments_field_none_when_absent -v
```

期望：`FAILED`（`Skill` 上没有 `arguments` 属性）

- [ ] **Step 3: 给 `Skill` 模型加字段**

修改 `backend/choreo/models/skill.py`，在 `Skill` 类末尾加一行：

```python
class Skill(BaseModel):
    id: str
    category: str
    name: str
    description: str
    version: str
    author: str
    tags: list[str]
    content: str
    source: Literal["manual", "auto", "builtin", "ai_review"]
    state: Literal["active", "stale", "archived"]
    pinned: bool
    locked: bool
    use_count: int
    view_count: int
    patch_count: int
    last_activity_at: int | None
    last_reviewed_at: int | None
    last_reviewed_by: str | None
    arguments: str | None = None   # ← 新增
```

- [ ] **Step 4: 在 `store.py` 的 `_parse_dir` 读取 `arguments`**

找到 `_parse_dir` 方法（第 69-96 行），在 `return Skill(...)` 里加一行：

```python
    def _parse_dir(self, skill_dir: Path, usage_entry: dict) -> Skill | None:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        fm, body = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
        if not fm.get("description"):
            return None
        u = {**_DEFAULT_USAGE, **usage_entry}
        return Skill(
            id=f"{skill_dir.parent.name}/{skill_dir.name}",
            category=skill_dir.parent.name,
            name=skill_dir.name,
            description=fm.get("description", ""),
            version=fm.get("version", "1.0.0"),
            author=fm.get("author", "user"),
            tags=fm.get("tags") or [],
            content=body,
            source=u["source"],
            state=u["state"],
            pinned=bool(u["pinned"]),
            locked=bool(u["locked"]),
            use_count=int(u["use_count"]),
            view_count=int(u["view_count"]),
            patch_count=int(u["patch_count"]),
            last_activity_at=u["last_activity_at"],
            last_reviewed_at=u["last_reviewed_at"],
            last_reviewed_by=u["last_reviewed_by"],
            arguments=fm.get("arguments") or None,   # ← 新增
        )
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd backend && uv run pytest tests/test_skill_store.py -v
```

期望：所有测试 PASSED

- [ ] **Step 6: 提交**

```bash
git add backend/choreo/models/skill.py backend/choreo/skills/store.py backend/tests/test_skill_store.py
git commit -m "feat(skills): add optional arguments field parsed from SKILL.md frontmatter"
```

---

## Task 2: Frontend — 斜杠技能命令

**Files:**
- Modify: `frontend/src/api/skills.ts`
- Modify: `frontend/src/components/Chat/ChatInput.tsx`

### 背景

`ChatInput.tsx` 目前约 118 行，负责模型选择器 + 输入框 + 发送。本 task 在同文件里增加：斜杠检测、技能弹窗、命令模式 chip、展开逻辑。不新建文件。

### 步骤

- [ ] **Step 1: 在 `api/skills.ts` 的 `Skill` 接口加 `arguments` 字段**

找到 `export interface Skill {` 块，在 `last_reviewed_by` 后加一行：

```typescript
export interface Skill {
  id: string;
  category: string;
  name: string;
  description: string;
  version: string;
  author: string;
  tags: string[];
  content: string;
  source: "manual" | "auto" | "builtin" | "ai_review";
  state: "active" | "stale" | "archived";
  pinned: boolean;
  locked: boolean;
  use_count: number;
  view_count: number;
  patch_count: number;
  last_activity_at: number | null;
  last_reviewed_at: number | null;
  last_reviewed_by: string | null;
  arguments?: string;   // ← 新增
}
```

- [ ] **Step 2: 验证类型通过**

```bash
cd frontend && pnpm exec tsc --noEmit
```

期望：零错误

- [ ] **Step 3: 全量替换 `ChatInput.tsx`**

用以下完整实现替换 `frontend/src/components/Chat/ChatInput.tsx`：

```tsx
import { useState, useEffect, useCallback, useRef, KeyboardEvent } from "react";
import useSWR from "swr";
import type { Skill } from "@/api/skills";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const fetcher = (url: string) => fetch(`${API}${url}`).then((r) => r.json());

interface ModelInfo { name: string; model?: string; display_name?: string }
interface Props {
  onSend: (text: string, context: Record<string, unknown>) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [modelOpen, setModelOpen] = useState(false);

  // Slash command state
  const [slashSkillId, setSlashSkillId] = useState<string | null>(null);
  const [dropdownIdx, setDropdownIdx] = useState(0);

  const modelDropdownRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: models = [] } = useSWR<ModelInfo[]>("/models/", fetcher);
  const { data: activeData } = useSWR<{ active_model: string }>("/models/active", fetcher);
  const { data: allSkills = [] } = useSWR<Skill[]>("/api/skills/?", fetcher);

  // 初始化默认模型
  useEffect(() => {
    if (!selectedModel && activeData?.active_model) {
      setSelectedModel(activeData.active_model);
    }
  }, [activeData, selectedModel]);

  // 点击模型下拉外部关闭
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) {
        setModelOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // 当文字变化时重置弹窗高亮索引
  useEffect(() => {
    setDropdownIdx(0);
  }, [text]);

  // 技能弹窗过滤逻辑：未在命令模式 且 以 "/" 开头
  const slashQuery =
    slashSkillId === null && text.startsWith("/")
      ? text.slice(1).toLowerCase()
      : null;

  const filteredSkills: Skill[] =
    slashQuery !== null
      ? allSkills
          .filter(
            (s) =>
              s.state === "active" &&
              (s.id.toLowerCase().includes(slashQuery) ||
                s.description.toLowerCase().includes(slashQuery))
          )
          .slice(0, 6)
      : [];

  const showSkillDropdown = filteredSkills.length > 0;

  // 选中技能，进入命令模式
  const selectSkill = useCallback((skill: Skill) => {
    setSlashSkillId(skill.id);
    setText("");
    setDropdownIdx(0);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, []);

  // 清除命令模式
  const clearSlashMode = useCallback(() => {
    setSlashSkillId(null);
    setText("");
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, []);

  // 发送（含展开逻辑）
  const handleSend = useCallback(async () => {
    const hasContent = slashSkillId !== null || text.trim();
    if (!hasContent || disabled) return;

    let messageText = text.trim();

    if (slashSkillId) {
      const [category, name] = slashSkillId.split("/");
      try {
        const res = await fetch(`${API}/api/skills/${category}/${name}`);
        if (res.ok) {
          const skill: Skill = await res.json();
          const content = skill.content ?? "";
          const args = messageText;
          if (content.includes("$ARGUMENTS")) {
            messageText = content.replace(/\$ARGUMENTS/g, args);
          } else {
            messageText = args ? `${content}\n\n${args}` : content;
          }
        }
      } catch {
        // fetch 失败则把参数作为普通消息发送
      }
    }

    if (!messageText.trim()) return;

    const context: Record<string, unknown> = {};
    if (selectedModel) context.model_name = selectedModel;
    onSend(messageText, context);
    setText("");
    setSlashSkillId(null);
  }, [slashSkillId, text, disabled, selectedModel, onSend]);

  const handleKey = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // 弹窗导航
      if (showSkillDropdown) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setDropdownIdx((i) => Math.min(i + 1, filteredSkills.length - 1));
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setDropdownIdx((i) => Math.max(i - 1, 0));
          return;
        }
        if (e.key === "Enter" || e.key === "Tab") {
          e.preventDefault();
          selectSkill(filteredSkills[dropdownIdx]);
          return;
        }
        if (e.key === "Escape") {
          e.preventDefault();
          setText("");
          return;
        }
      }
      // 普通 Enter 发送
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [showSkillDropdown, filteredSkills, dropdownIdx, selectSkill, handleSend]
  );

  const currentModel = models.find((m) => m.name === selectedModel);
  const displayLabel = currentModel?.display_name ?? currentModel?.name ?? selectedModel;
  const canSend = !disabled && (slashSkillId !== null || !!text.trim());

  return (
    <div className="px-6 pb-4 pt-3">
      <div className="max-w-[740px] mx-auto">
        {/* 模型选择器 */}
        {models.length > 0 && (
          <div className="flex items-center gap-2 mb-2 px-1" ref={modelDropdownRef}>
            <span className="text-[10px] text-[#aaa] dark:text-[#555]">模型</span>
            <div className="relative">
              <button
                onClick={() => setModelOpen((v) => !v)}
                className="flex items-center gap-1.5 px-2 py-0.5 rounded-md text-[11px] bg-[#e8e4dc] dark:bg-[#1e1e1e] text-[#555] dark:text-[#888] hover:bg-[#ddd9d0] dark:hover:bg-[#252525] transition-colors"
              >
                <span>{displayLabel || "选择模型"}</span>
                <svg className="w-2.5 h-2.5 opacity-50" viewBox="0 0 10 6" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M1 1l4 4 4-4" />
                </svg>
              </button>
              {modelOpen && (
                <div className="absolute bottom-full mb-1 left-0 min-w-[140px] bg-white dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] rounded-lg shadow-md py-1 z-50">
                  {models.map((m) => (
                    <button
                      key={m.name}
                      onClick={() => { setSelectedModel(m.name); setModelOpen(false); }}
                      className={`w-full text-left px-3 py-1.5 text-[11px] hover:bg-[#f5f2eb] dark:hover:bg-[#252525] transition-colors ${
                        m.name === selectedModel
                          ? "text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                          : "text-[#555] dark:text-[#888]"
                      }`}
                    >
                      {m.display_name ?? m.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 输入区域（含弹窗定位容器） */}
        <div className="relative">
          {/* 技能选择弹窗 */}
          {showSkillDropdown && (
            <div className="absolute bottom-full left-0 right-0 mb-1.5 bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-xl shadow-lg overflow-hidden z-50">
              {filteredSkills.map((skill, i) => (
                <button
                  key={skill.id}
                  onMouseDown={(e) => { e.preventDefault(); selectSkill(skill); }}
                  className={`w-full text-left px-3 py-2 transition-colors ${
                    i === dropdownIdx
                      ? "bg-[#f5f2eb] dark:bg-[#252525]"
                      : "hover:bg-[#f9f7f3] dark:hover:bg-[#1f1f1f]"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-[#888] dark:text-[#555]">/</span>
                    <span className="text-[11.5px] font-medium text-[#1a1a1a] dark:text-[#e8e8e8]">{skill.id}</span>
                  </div>
                  <p className="text-[10px] text-[#999] dark:text-[#555] truncate mt-0.5">{skill.description}</p>
                  {skill.arguments && (
                    <p className="text-[9.5px] text-[#bbb] dark:text-[#444] mt-0.5">参数：{skill.arguments}</p>
                  )}
                </button>
              ))}
            </div>
          )}

          {/* 输入框主体 */}
          <div className="flex flex-col bg-white dark:bg-[#1a1a1a] border border-[#d6d0c7] dark:border-[#252525] rounded-[13px] px-3.5 py-2.5 shadow-sm dark:shadow-none">
            {/* 命令模式 chip */}
            {slashSkillId && (
              <div className="flex items-center gap-1.5 mb-2">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-900/50 text-[11px] font-mono text-blue-600 dark:text-blue-400 leading-none">
                  /{slashSkillId}
                  <button
                    onClick={clearSlashMode}
                    className="ml-0.5 text-blue-400 dark:text-blue-600 hover:text-blue-600 dark:hover:text-blue-400 transition-colors leading-none"
                    tabIndex={-1}
                  >
                    ×
                  </button>
                </span>
              </div>
            )}

            {/* 文本输入 + 发送按钮 */}
            <div className="flex items-end gap-2.5">
              <textarea
                ref={textareaRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={handleKey}
                placeholder={
                  slashSkillId
                    ? "输入参数（可选）…"
                    : "描述你想自动化的任务，或输入 / 选择技能…"
                }
                disabled={disabled}
                rows={2}
                className="flex-1 resize-none outline-none bg-transparent text-[12.5px] text-[#1a1a1a] dark:text-[#e8e8e8] placeholder-[#bbb] dark:placeholder-[#3a3a3a]"
              />
              <button
                onClick={handleSend}
                disabled={!canSend}
                className="w-7 h-7 rounded-lg bg-[#1e293b] dark:bg-[#252525] text-white dark:text-[#aaa] flex items-center justify-center text-sm flex-shrink-0 disabled:opacity-30 hover:opacity-80 transition-opacity"
              >
                ↑
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: TypeScript 类型检查**

```bash
cd frontend && pnpm exec tsc --noEmit
```

期望：零错误

- [ ] **Step 5: 手动冒烟测试**

启动开发服务器：
```bash
cd frontend && pnpm dev
```

按顺序验证：

1. 打开 `http://localhost:5173`，在聊天输入框输入 `/`
   - 期望：弹出技能列表（若无技能则弹窗不出现，属正常）

2. 继续输入 `/git`（如有 git 类技能）
   - 期望：列表过滤

3. 按 ↓ 导航到第二项，按 Enter 选中
   - 期望：弹窗关闭，输入框上方出现蓝色 chip `/ git/weekly-report`，placeholder 变为"输入参数（可选）…"

4. 输入"本周"，按 Enter 发送
   - 期望：chip 消失，消息以展开后的技能内容发出（在 DevTools Network 可查 SSE 请求 body）

5. 点击 chip 上的 `×`
   - 期望：退出命令模式，输入框清空

6. 输入不带 `/` 的普通消息，确认原有发送行为不变

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/skills.ts frontend/src/components/Chat/ChatInput.tsx
git commit -m "feat(chat): add slash skill command — /category/name expands SKILL.md content before sending"
```

---

## 验收标准

- [ ] 输入 `/` 弹出技能列表，继续输入可过滤
- [ ] 键盘 ↑↓ 导航，Enter/Tab 选中，Escape 关闭弹窗
- [ ] 选中后出现蓝色命令 chip，点 `×` 退出命令模式
- [ ] 发送时技能 content 中的 `$ARGUMENTS` 被替换为用户输入
- [ ] 无 `$ARGUMENTS` 时：有参数则追加，无参数则原样发送
- [ ] 技能不存在时：文本原样发送，不报错
- [ ] 原有功能（模型选择器、普通消息发送）不受影响
- [ ] `tsc --noEmit` 零错误
- [ ] 后端 pytest 全部通过
