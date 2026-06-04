# backend/choreo/skills/curator.py
"""Periodic skill library curator — Hermes-inspired.

Two-phase cycle (default every 24 h):
  Phase 1 (heuristic): archive agent-created skills that haven't been used
                        in `stale_after_days` days and aren't pinned.
  Phase 2 (LLM):       consolidate overlapping / redundant agent skills
                        via a dedicated curator agent.

Only touches skills with source="agent" or source="manual".
Never touches source="builtin" or locked=True skills.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from choreo.models.skill import SkillPatch

logger = logging.getLogger(__name__)

_PROTECTED_SOURCES = {"builtin"}
_CURATOR_LOG_MAX = 50


class _RunLog:
    """Collects log lines and writes each one immediately to a progress file."""

    def __init__(self, progress_path: Path) -> None:
        self._lines: list[dict] = []
        self._path = progress_path
        self._path.unlink(missing_ok=True)

    def append(self, entry: dict) -> None:
        self._lines.append(entry)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @property
    def lines(self) -> list[dict]:
        return self._lines


class SkillCurator:
    def __init__(self, cfg: dict | None = None) -> None:
        c = cfg or {}
        self.enabled: bool = c.get("enabled", True)
        self.interval_hours: float = float(c.get("interval_hours", 24))
        self.stale_after_days: int = int(c.get("stale_after_days", 30))
        self.min_use_count: int = int(c.get("min_use_count_to_protect", 3))
        self._task: asyncio.Task | None = None

    # ── lifecycle ─────────────────────────────────────────────────────

    def start(self) -> None:
        if not self.enabled:
            return
        self._task = asyncio.create_task(self._loop(), name="skill-curator")
        logger.info(
            "SkillCurator started (interval=%.1fh, stale_after=%dd)",
            self.interval_hours,
            self.stale_after_days,
        )

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval_hours * 3600)
            try:
                await self.run_once()
            except Exception:
                logger.warning("Curator cycle failed", exc_info=True)

    # ── public: run a single cycle ────────────────────────────────────

    async def run_once(self) -> dict[str, Any]:
        logger.info("Curator cycle starting")
        from choreo.skills import get_skill_store
        progress_path = get_skill_store()._root / ".curator_progress.jsonl"

        start_ts = int(time.time())
        t0 = time.time()
        log = _RunLog(progress_path)

        archived = await self._archive_stale(log)
        consolidated = await self._llm_consolidate(log)

        elapsed = round(time.time() - t0, 1)
        log.append({"type": "done", "text": f"整理完成 · 归档 {len(archived)} · 合并 {len(consolidated)} · 耗时 {elapsed}s"})

        result: dict[str, Any] = {
            "ts": start_ts,
            "archived": archived,
            "consolidated": consolidated,
            "lines": log.lines,
        }
        await self._append_curator_log(result)
        progress_path.unlink(missing_ok=True)  # done, remove progress file
        logger.info(
            "Curator cycle done: archived=%d consolidated=%d",
            len(archived),
            len(consolidated),
        )
        return result

    # ── Phase 1: heuristic archive ────────────────────────────────────

    async def _archive_stale(self, log: _RunLog) -> list[str]:
        from choreo.skills import get_skill_store

        store = get_skill_store()
        all_skills = await store.list_all()
        cutoff = time.time() - self.stale_after_days * 86400
        archived: list[str] = []

        log.append({"type": "phase", "text": "阶段一：归档闲置技能"})
        log.append({"type": "info", "text": f"扫描 {len(all_skills)} 个技能…"})

        for skill in all_skills:
            if skill.state == "archived":
                continue
            if skill.source in _PROTECTED_SOURCES:
                log.append({"type": "skip", "text": f"跳过  {skill.id}  （内置，保留）"})
                continue
            if skill.locked or skill.pinned:
                log.append({"type": "skip", "text": f"跳过  {skill.id}  （已锁定/固定）"})
                continue
            last_active = skill.last_activity_at or 0
            days_since = int((time.time() - last_active) / 86400) if last_active else 999
            if last_active < cutoff and skill.use_count < self.min_use_count:
                try:
                    await store.update(skill.id, SkillPatch(state="archived"))
                    archived.append(skill.id)
                    log.append({"type": "archive", "text": f"归档  {skill.id}  （最后使用：{days_since} 天前）"})
                    logger.debug("Curator archived stale skill: %s", skill.id)
                except Exception:
                    log.append({"type": "error", "text": f"归档失败  {skill.id}"})
                    logger.warning("Could not archive skill %s", skill.id, exc_info=True)

        log.append({"type": "ok", "text": f"归档完成：{len(archived)} 个"})
        return archived

    # ── Phase 2: LLM consolidation ────────────────────────────────────

    async def _llm_consolidate(self, log: _RunLog) -> list[str]:
        from choreo.skills import get_skill_store

        store = get_skill_store()
        all_skills = await store.list_all(state="active")

        candidate_skills = [
            s for s in all_skills
            if s.source not in _PROTECTED_SOURCES and not s.locked
        ]

        log.append({"type": "phase", "text": "阶段二：合并重复技能（LLM 分析）"})

        if len(candidate_skills) < 2:
            log.append({"type": "info", "text": "候选技能不足 2 个，跳过合并"})
            log.append({"type": "ok", "text": "合并完成：0 组"})
            return []

        log.append({"type": "info", "text": f"候选技能 {len(candidate_skills)} 个，交由 LLM 分析…"})
        skill_index = _build_skill_index(candidate_skills)

        try:
            consolidated, agent_lines = await _run_curator_agent(skill_index)
            for line in agent_lines:
                log.append(line)
            log.append({"type": "ok", "text": f"合并完成：{len(consolidated)} 组"})
            return consolidated
        except Exception:
            logger.warning("LLM consolidation failed", exc_info=True)
            log.append({"type": "error", "text": "LLM 分析失败，跳过合并"})
            return []

    # ── curator log ───────────────────────────────────────────────────

    async def _append_curator_log(self, entry: dict) -> None:
        from choreo.skills import get_skill_store
        store = get_skill_store()
        log_path = store._root / ".curator_log.jsonl"

        def _write() -> None:
            lines: list[str] = []
            if log_path.exists():
                lines = log_path.read_text(encoding="utf-8").splitlines()
            lines.append(json.dumps(entry, ensure_ascii=False))
            if len(lines) > _CURATOR_LOG_MAX:
                lines = lines[-_CURATOR_LOG_MAX:]
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        await asyncio.to_thread(_write)


# ── helpers ────────────────────────────────────────────────────────────

def _build_skill_index(skills) -> str:
    lines = ["以下是所有 agent/manual 技能（可参与整合），每行格式：skill_id | use_count | 描述 | related"]
    for s in skills:
        related = f" | related: {', '.join(s.related_skills)}" if s.related_skills else ""
        lines.append(f"{s.id} | used={s.use_count} | {s.description[:100]}{related}")
    return "\n".join(lines)


_CURATOR_SYSTEM_PROMPT = """\
你是 Choreo 的技能库馆长（Curator）。你的任务是整合技能库，合并重复技能，提升质量。

## 合并判断标准（满足任一条即应合并）

- **同一意图**：两个技能响应的用户请求高度相似，只是表达不同（如"打招呼"和"友好回复"）
- **子集关系**：一个技能是另一个技能的特殊情况（如"只说你好"是"友好回复"的子集）
- **功能重叠 ≥ 60%**：大多数使用场景可以由其中一个技能覆盖

## 合并操作步骤

1. 用 skill_view 读取两个技能的全文
2. 保留 use_count 更高的那个（它更常用），用 skill_patch 更新内容（追加缺失内容，不丢现有内容）
3. 用 skill_archive 归档被合并掉的那个，reason 写清楚合并到哪里

## 绝对不能合并的情况

- **操作类型不同** — "agent 直接回复" vs "创建/修改文件" 是两类完全不同的操作，即使主题相同也不能合并。例如：
  - `说你好`（agent 回复文字）和 `创建 say-hello 脚本`（写入 .sh 文件）→ **不合并**
  - `发送通知`（调用 API）和 `写通知日志`（写文件）→ **不合并**
- source=builtin 或 locked=true 的技能（工具会拒绝）

## 对每组候选技能，你必须明确表态

读完技能内容后，逐一写出判断：
- "skill-a 和 skill-b：同一意图 → 合并，保留 skill-a"
- "skill-c 和 skill-d：操作类型不同 → 不合并"

不能只说"经过分析"，必须给出明确的合并/不合并结论。

## 可用工具

- skill_view(skill_id): 读技能全文
- skill_patch(skill_id, content, description, tags): 更新技能
- skill_archive(skill_id, reason): 归档一个技能（设置 state=archived）

## 输出

最后输出一行简短总结，例如：
"整合完成：合并 2 对，归档 2 个，无操作 4 个。"
"""


async def _run_curator_agent(skill_index: str) -> tuple[list[str], list[dict]]:
    from langchain.agents import create_agent
    from choreo.skills.curator_tools import skill_view, skill_patch, skill_archive

    llm = _load_curator_model()
    agent = create_agent(
        model=llm,
        tools=[skill_view, skill_patch, skill_archive],
        system_prompt=_CURATOR_SYSTEM_PROMPT,
    )

    user_msg = f"请整合以下技能库（有 skill 才需要整合，没有可直接完成）：\n\n{skill_index}"
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_msg}]},
        config={"configurable": {"thread_id": f"curator-{int(time.time())}"}},
    )

    from langchain_core.messages import AIMessage as _AIMessage

    consolidated: list[str] = []
    agent_lines: list[dict] = []
    patched: set[str] = set()

    for msg in result.get("messages", []):
        # Only process AIMessage — skip HumanMessage and ToolMessage
        if not isinstance(msg, _AIMessage):
            continue

        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            # Final AI summary (no tool calls) — emit each non-empty line separately
            content = getattr(msg, "content", "") or ""
            if isinstance(content, str) and content.strip():
                for line in content.strip().splitlines():
                    line = line.strip()
                    if line:
                        agent_lines.append({"type": "llm", "text": line[:300]})
            continue

        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {})
            if isinstance(args, dict):
                sid = args.get("skill_id")
            else:
                sid = getattr(args, "skill_id", None)

            if name == "skill_archive" and sid:
                reason = (args.get("reason") if isinstance(args, dict) else getattr(args, "reason", "")) or ""
                target = patched - {sid}
                if target:
                    target_name = next(iter(target))
                    agent_lines.append({"type": "merge", "text": f"合并  {sid} → {target_name}"})
                else:
                    agent_lines.append({"type": "archive", "text": f"归档  {sid}  （{reason}）"})
                consolidated.append(sid)
            elif name == "skill_patch" and sid:
                if sid not in patched:
                    agent_lines.append({"type": "merge", "text": f"更新  {sid}  （合并内容）"})
                    patched.add(sid)
            elif name == "skill_view" and sid:
                agent_lines.append({"type": "info", "text": f"查看  {sid}"})

    return consolidated, agent_lines


def _load_curator_model():
    from choreo.model_factory import load_model
    from choreo.config import settings
    curator_model = (settings.CURATOR or {}).get("model") or None
    return load_model(curator_model)
