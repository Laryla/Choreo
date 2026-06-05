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
    from choreo.config import settings
    review_model_name = settings.REVIEW_MODEL or None
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
你是 Choreo 的技能复盘 agent。你的唯一职责是：
更新已有技能，让 agent 在这个用户的环境和工作方式下越来越有效。

## 本次已知信息

本次对话中 agent 主动查阅了以下技能（已确认调用）：
{invoked_list}

这些技能是优先 patch 的候选。用 skill_view 读取全文后再决定是否修改。

## 你只能做一件事：patch 现有技能

**严格禁止调用 skill_manager(action=create)。新技能的创建由用户确认后完成，不在你的职责范围内。**

可以 patch 的情形：
- 本次对话修正或补充了某个现有技能的内容
- 发现了现有技能中的错误或遗漏
- 用户的工作方式/偏好有了新的体现（如提交格式、命名习惯）
- 踩到了坑，需要在现有技能里加避坑说明

patch 质量要求：
- 先 skill_view 读全文，再决定改哪里
- 只追加或修正，不整体重写，patch 后总大小不超过 15KB
- 记录"下次怎么做"，不记录"这次发生了什么"

## 大多数对话什么都不做

以下情况直接退出，不调任何工具：
- 对话内容简单（问答、解释、闲聊）
- 无现有技能与本次对话相关
- 本次对话没有产生可复用的新知识
- 纯环境错误（缺包、权限、网络）\
"""


_EVALUATE_SYSTEM_PROMPT = """\
你是技能价值评估器。大多数对话不值得保存为技能，你的默认答案是"不保存"。

仅当同时满足以下全部条件才输出建议：
1. 对话包含 3 步以上形成完整可复现的工作流
2. 流程具有项目或环境特异性（不是 LLM 的通识知识）
3. 未来遇到相似场景可以直接套用
4. 不是一次性任务，有复用价值

遇到以下任一条，直接输出 {"suggest": false}：
- 问答、解释、讨论（即使内容很技术）
- 单步 fix 或一次性调试
- 环境安装/配置/权限问题
- 对话轮次少于 5 轮
- 结果与特定项目强绑定，换个项目无法复用

输出严格 JSON，不要任何额外文字：
{"suggest": true, "category": "kebab-case分类", "name": "kebab-case名称", "description": "≤80字说明何时用", "content_draft": "Markdown格式的操作步骤"}
或
{"suggest": false}\
"""


async def evaluate_for_suggestion(messages: list) -> dict | None:
    """快速评估对话是否值得保存为技能，返回建议 dict 或 None。"""
    try:
        from choreo.model_factory import load_model
        from langchain_core.messages import HumanMessage, SystemMessage

        history = _format_messages_for_review(messages)
        if not history or history == "（无有效对话内容）":
            return None

        llm = load_model()
        resp = await llm.ainvoke([
            SystemMessage(content=_EVALUATE_SYSTEM_PROMPT),
            HumanMessage(content=history[:3000]),
        ])

        import json as _json
        text = str(resp.content).strip()
        # 提取 JSON（有时模型会加 ```json 围栏）
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        data = _json.loads(text)
        if not data.get("suggest"):
            return None
        return {
            "category": data.get("category", "general"),
            "name": data.get("name", "untitled"),
            "description": data.get("description", ""),
            "content_draft": data.get("content_draft", ""),
        }
    except Exception as exc:
        logger.debug("evaluate_for_suggestion 失败（静默）: %r", exc)
        return None


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
