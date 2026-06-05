# Curator Run Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在技能管理页面右侧空状态区（没有选中技能时）展示 Curator 管理面板，包含「立即整理」按钮，调用 `POST /api/skills/curator/run`，轮询日志检测完成，展示结果摘要。

**Architecture:** 按钮触发后端后台任务（立即返回 `{"status": "started"}`），前端记录触发时刻，每 2 秒轮询 `GET /api/skills/curator_log`，一旦出现比触发时刻更新的日志条目，停止轮询并展示结果（归档 N 个，合并 M 个）。空状态区（右侧主内容面板、无技能选中时）替换原有「从左侧选择一个技能查看详情」占位符，改为有实际功能的 Curator 面板。轮询超时 120 秒后自动停止。

**Tech Stack:** React, TypeScript, useSWR, fetch（已有全局 token 注入）

---

## File Structure

| 文件 | 变更 |
|------|------|
| `frontend/src/api/skills.ts` | 添加 `runCurator()` 和 `getCuratorLog()` 两个函数 |
| `frontend/src/pages/CustomizeSkillsPage.tsx` | 添加 `CuratorPanel` 组件（内联）和状态逻辑 |

---

### Task 1: 在 skills API 模块添加 curator 函数

**Files:**
- Modify: `frontend/src/api/skills.ts`

- [ ] **Step 1: 在 `frontend/src/api/skills.ts` 末尾添加 curator 接口类型和两个函数**

在文件末尾（`getReviewLog` 之后）追加：

```ts
export interface CuratorLogEntry {
  ts: number;           // Unix 时间戳（秒）
  archived: string[];   // 被归档的技能 ID 列表
  consolidated: string[]; // 被合并的技能 ID 列表
}

export const runCurator = (): Promise<{ status: string }> =>
  fetch(`${BASE}/curator/run`, { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

export const getCuratorLog = (limit = 5): Promise<CuratorLogEntry[]> =>
  fetch(`${BASE}/curator_log?limit=${limit}`).then((r) => r.json());
```

- [ ] **Step 2: 手动验证 — 启动后端，在浏览器控制台执行**

```js
fetch("http://localhost:8000/api/skills/curator/run", {method:"POST"})
  .then(r=>r.json()).then(console.log)
// 预期输出: {status: "started"}

fetch("http://localhost:8000/api/skills/curator_log?limit=5")
  .then(r=>r.json()).then(console.log)
// 预期输出: 数组（可能为空）
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/skills.ts
git commit -m "feat(skills): add runCurator and getCuratorLog API functions"
```

---

### Task 2: 在 CustomizeSkillsPage 添加 CuratorPanel

**Files:**
- Modify: `frontend/src/pages/CustomizeSkillsPage.tsx`

`CustomizeSkillsPage` 右侧面板在没有选中技能时显示空状态（当前是「从左侧选择一个技能查看详情」）。用 Curator 管理面板替换这个空状态，放在右侧主内容区中央。

- [ ] **Step 1: 在 `CustomizeSkillsPage.tsx` 的 import 行添加新 API 函数**

找到：
```ts
import type { Skill, SkillPatch, ReviewLogEntry } from "@/api/skills";
import { patchSkill, deleteSkill, readSkillFile, getReviewLog } from "@/api/skills";
```

替换为：
```ts
import type { Skill, SkillPatch, ReviewLogEntry, CuratorLogEntry } from "@/api/skills";
import { patchSkill, deleteSkill, readSkillFile, getReviewLog, runCurator, getCuratorLog } from "@/api/skills";
```

- [ ] **Step 2: 在 `CustomizeSkillsPage` 函数体内添加 curator 状态（在现有 state 声明之后）**

找到：
```ts
  const [busy, setBusy] = useState(false);
  const [lastReview, setLastReview] = useState<ReviewLogEntry | null>(null);
```

在这两行之后追加：
```ts
  const [curatorRunning, setCuratorRunning] = useState(false);
  const [curatorResult, setCuratorResult] = useState<CuratorLogEntry | null>(null);
  const [curatorError, setCuratorError] = useState<string | null>(null);
```

- [ ] **Step 3: 添加 `handleRunCurator` 函数（在现有 `patch` 函数之前）**

找到：
```ts
  const patch = async (body: SkillPatch) => {
```

在它之前插入：
```ts
  const handleRunCurator = async () => {
    setCuratorRunning(true);
    setCuratorResult(null);
    setCuratorError(null);
    const triggeredAt = Math.floor(Date.now() / 1000);

    try {
      await runCurator();
    } catch {
      setCuratorError("启动失败，请检查后端日志");
      setCuratorRunning(false);
      return;
    }

    // 轮询日志，等待比触发时刻更新的条目出现（最多 120 秒）
    const deadline = Date.now() + 120_000;
    const poll = async () => {
      if (Date.now() > deadline) {
        setCuratorError("超时未完成，请稍后查看日志");
        setCuratorRunning(false);
        return;
      }
      const entries = await getCuratorLog(5).catch(() => [] as CuratorLogEntry[]);
      const fresh = entries.find((e) => e.ts > triggeredAt);
      if (fresh) {
        setCuratorResult(fresh);
        setCuratorRunning(false);
        mutate(); // 刷新技能列表
      } else {
        setTimeout(poll, 2000);
      }
    };
    setTimeout(poll, 2000);
  };

```

- [ ] **Step 4: 用 Curator 面板替换右侧空状态区**

在 `CustomizeSkillsPage.tsx` 找到（约第 438 行）：

```tsx
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center text-[#ccc] dark:text-[#333] gap-3">
          <svg className="w-14 h-14 opacity-30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.2">
            <path d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18" />
          </svg>
          <p className="text-[13px]">从左侧选择一个技能查看详情</p>
        </div>
      )}
```

替换为：

```tsx
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-8 px-12">
          {/* Curator 管理面板 */}
          <div className="w-full max-w-[480px] rounded-xl border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] p-6">
            <div className="flex items-center gap-2.5 mb-1">
              <span className="text-[18px]">✦</span>
              <h3 className="text-[14px] font-semibold text-[#1e293b] dark:text-[#e8e8e8]">技能库整理</h3>
            </div>
            <p className="text-[12px] text-[#888] dark:text-[#555] mb-5 leading-relaxed">
              自动归档 30 天未使用的技能，合并重复技能。每 24 小时自动执行一次。
            </p>

            <button
              onClick={handleRunCurator}
              disabled={curatorRunning}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] font-medium hover:bg-[#0f172a] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {curatorRunning ? (
                <>
                  <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  整理中…
                </>
              ) : (
                "立即整理"
              )}
            </button>

            {curatorError && (
              <p className="mt-3 text-[12px] text-red-500 dark:text-red-400">{curatorError}</p>
            )}

            {curatorResult && !curatorRunning && (
              <div className="mt-3 px-3 py-2 rounded-lg bg-[#f5f2eb] dark:bg-[#141414] text-[12px] text-[#555] dark:text-[#888]">
                ✓ 完成 ·{" "}
                {curatorResult.archived.length > 0
                  ? `归档 ${curatorResult.archived.length} 个`
                  : "无归档"}{" "}
                ·{" "}
                {curatorResult.consolidated.length > 0
                  ? `合并 ${curatorResult.consolidated.length} 个`
                  : "无合并"}
              </div>
            )}
          </div>

          <p className="text-[12px] text-[#ccc] dark:text-[#333]">从左侧选择一个技能查看详情</p>
        </div>
      )}
```

- [ ] **Step 5: 启动前端验证**

```bash
cd frontend && pnpm dev
```

打开 `/customize/skills`，未选中任何技能时确认：
1. 右侧主内容区显示「技能库整理」卡片 + 「立即整理」按钮
2. 点击后按钮变为「整理中…」带旋转动画
3. 任务完成后显示「✓ 完成 · 无归档 · 无合并」（或实际数字）
4. 技能列表自动刷新
5. 卡片下方保留「从左侧选择一个技能查看详情」提示

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CustomizeSkillsPage.tsx
git commit -m "feat(skills): add curator run button with polling result display"
```

---

## Self-Review

**Spec coverage:**
- ✅ 按钮调用 `POST /api/skills/curator/run`
- ✅ 展示执行状态（loading spinner）
- ✅ 轮询检测完成（比触发时刻更新的日志条目）
- ✅ 展示结果（归档 N / 合并 M）
- ✅ 完成后刷新技能列表
- ✅ 超时处理（120 秒）

**Placeholder scan:** 无 TBD/TODO

**Type consistency:**
- `CuratorLogEntry.ts` / `CuratorLogEntry.archived` / `CuratorLogEntry.consolidated` 在 Task 1 定义，Task 2 使用 ✅
- `runCurator` / `getCuratorLog` 在 Task 1 定义，Task 2 import 和使用 ✅
