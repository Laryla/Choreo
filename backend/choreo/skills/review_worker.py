import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from choreo.skills import get_skill_store

logger = logging.getLogger(__name__)

# Per-thread concurrency state
_locks: dict[str, asyncio.Lock] = {}
_pending: dict[str, tuple[list, list[str]]] = {}


def _get_lock(thread_id: str) -> asyncio.Lock:
    if thread_id not in _locks:
        _locks[thread_id] = asyncio.Lock()
    return _locks[thread_id]


def extract_invoked_skills(messages: list) -> list[str]:
    """Deterministically extract skill read calls from LangGraph message history."""
    seen: list[str] = []
    for msg in messages:
        tool_calls: Any = None
        if hasattr(msg, "tool_calls"):
            tool_calls = msg.tool_calls
        elif isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")

        if not tool_calls:
            continue

        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name")
                args = tc.get("args", {})
            else:
                name = getattr(tc, "name", None)
                args = getattr(tc, "args", {})

            # skill_manager(action="read") or legacy skill_view
            if name == "skill_manager":
                action = args.get("action") if isinstance(args, dict) else getattr(args, "action", None)
                if action != "read":
                    continue
            elif name != "skill_view":
                continue

            skill_id = args.get("skill_id") if isinstance(args, dict) else getattr(args, "skill_id", None)
            if skill_id and skill_id not in seen:
                seen.append(skill_id)

    return seen


async def maybe_start_review(
    thread_id: str,
    messages: list,
    invoked_skills: list[str],
) -> bool:
    """Fire background review, or queue it if one is already running.

    Returns True if a new review task was started, False if queued.
    """
    lock = _get_lock(thread_id)

    if lock.locked():
        _pending[thread_id] = (messages, invoked_skills)
        return False

    asyncio.create_task(_run_review_with_pending(thread_id, messages, invoked_skills))
    return True


async def _run_review_with_pending(thread_id: str, messages: list, invoked_skills: list[str]) -> None:
    """Run review, then drain the pending slot if populated during this run."""
    lock = _get_lock(thread_id)
    async with lock:
        await _run_review(thread_id, messages, invoked_skills)

    pending = _pending.pop(thread_id, None)
    if pending:
        msgs, skills = pending
        asyncio.create_task(_run_review_with_pending(thread_id, msgs, skills))


def _load_review_model():
    from choreo.model_factory import load_model
    yaml_path = Path(__file__).parent.parent.parent / "config.yaml"
    try:
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        review_model_name = cfg.get("review_model")
    except Exception:
        review_model_name = None
    return load_model(review_model_name)


def _format_messages_for_review(messages: list) -> str:
    """Summarize conversation history for the review prompt."""
    lines = []
    for msg in messages:
        if hasattr(msg, "type"):
            role = msg.type
            content = getattr(msg, "content", "")
        elif isinstance(msg, dict):
            role = msg.get("type") or msg.get("role", "unknown")
            content = msg.get("content", "")
        else:
            continue

        if isinstance(content, list):
            text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = " ".join(text_parts)
        content = str(content)

        if role in ("human", "user"):
            lines.append(f"用户: {content}")
        elif role in ("ai", "assistant") and content.strip():
            lines.append(f"Agent: {content[:800]}" + ("..." if len(content) > 800 else ""))

    return "\n\n".join(lines) if lines else "（无有效对话内容）"


def _extract_review_actions(messages: list) -> tuple[list[str], list[str]]:
    """Return (updated_skill_ids, created_skill_ids) from review agent output messages."""
    updated: list[str] = []
    created: list[str] = []

    for msg in messages:
        tool_calls: Any = None
        if hasattr(msg, "tool_calls"):
            tool_calls = msg.tool_calls
        elif isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        for tc in tool_calls:
            if isinstance(tc, dict):
                name, args = tc.get("name"), tc.get("args", {})
            else:
                name, args = getattr(tc, "name", None), getattr(tc, "args", {})

            action = args.get("action") if isinstance(args, dict) else getattr(args, "action", None)
            if name in ("skill_patch",) or (name == "skill_manager" and action == "patch"):
                sid = args.get("skill_id") if isinstance(args, dict) else getattr(args, "skill_id", None)
                if sid and sid not in updated:
                    updated.append(sid)
            elif name in ("skill_create",) or (name == "skill_manager" and action == "create"):
                cat = args.get("category") if isinstance(args, dict) else getattr(args, "category", None)
                nm = args.get("name") if isinstance(args, dict) else getattr(args, "name", None)
                if cat and nm:
                    sid = f"{cat}/{nm}"
                    if sid not in created:
                        created.append(sid)

    return updated, created


_REVIEW_SYSTEM_PROMPT = """\
你是 Choreo 的技能复盘 agent。你的核心使命是：
让 agent 在这个用户的环境和工作方式下越来越有效。

## 本次已知信息

本次对话中 agent 主动查阅了以下技能（已确认调用）：
{invoked_list}

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

## 技能内容格式

新建技能前，必须先调用 skill_view 查看一个现有的同类技能（优先看 builtin 技能，
如 git/weekly-report、python/uv-project、debug/error-diagnosis），以它的结构和风格为参照。
不要凭空发明格式。

description 规则：
- ≤80 字符
- 直接回答"何时用"，例如：
  "Run Python projects with uv (install, add, run)."
  "Diagnose errors by reading traceback bottom-up."

related_skills：如果互补技能已存在，在 skill_create/skill_patch 时传入 related_skills 参数
（如 ['git/commit-message', 'debug/error-diagnosis']）。

不要用流水账叙述，不要写"这次发生了什么"，只写"下次怎么做"。

## 明确不写的情况

- 内置技能（source=builtin）— 工具会拒绝
- 被锁定的技能（locked=true）— 工具会拒绝
- 纯环境错误（缺包、权限、网络）— 不是可复用的知识
- 完全一次性的任务，未来不可能遇到相同场景
- 对话内容过于简单或无实质内容（如纯问候）— 直接退出即可，无需强行写\
"""


async def _run_review(thread_id: str, messages: list, invoked_skills: list[str]) -> None:
    """Core review worker: runs a restricted stateless agent to update skills."""
    from langchain.agents import create_agent
    from choreo.agents.tools.skill_tool import skill_manager

    try:
        review_llm = _load_review_model()

        invoked_list = "\n".join(f"- {s}" for s in invoked_skills) if invoked_skills else "（本次无已记录调用）"
        system_prompt = _REVIEW_SYSTEM_PROMPT.format(invoked_list=invoked_list)
        history_text = _format_messages_for_review(messages)

        review_agent = create_agent(
            model=review_llm,
            tools=[skill_manager],
            system_prompt=system_prompt,
        )

        result = await review_agent.ainvoke(
            {"messages": [{"role": "user", "content": history_text}]},
            config={"configurable": {"thread_id": f"review-{thread_id}"}},
        )

        updated, created = _extract_review_actions(result.get("messages", []))

        store = get_skill_store()
        await store.append_review_log({
            "thread_id": thread_id,
            "ts": int(time.time()),
            "updated": updated,
            "created": created,
        })

        logger.info(
            "Review complete for %s: updated=%s created=%s", thread_id, updated, created
        )

    except Exception:
        logger.warning("Background review failed for thread %s", thread_id, exc_info=True)
