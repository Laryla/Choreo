"""
task tool — dispatches a sub-task to a specialized sub-agent.

The main Choreo agent calls task(subagent_type, description, prompt) to delegate
work to a focused sub-agent (research, coder, executor). Each sub-agent has its own
tool set and system prompt; it cannot call task() recursively (disallowed_tools).
"""
from __future__ import annotations

import logging
import uuid

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


_TOOLS_CACHE: list | None = None


def _get_all_tools() -> list:
    """Build the full tool list without importing from choreo_agent (avoids circular import)."""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE
    from choreo.agents.tools import (
        read_git_log, send_notification,
        read_file, write_file, edit_file, list_dir, grep, bash, skill_view,
    )
    from choreo.agents.tools.skill_tool import skill_patch, skill_create
    from choreo.agents.tools.mcp_tool import mcp_call, mcp_describe
    from choreo.agents.tools.web_tools import web_search, fetch_url

    _TOOLS_CACHE = [
        read_git_log, send_notification,
        read_file, write_file, edit_file, list_dir, grep, bash, skill_view,
        skill_patch, skill_create,
        mcp_call, mcp_describe,
        web_search, fetch_url,
    ]
    return _TOOLS_CACHE


@tool
async def task(subagent_type: str, description: str, prompt: str) -> str:
    """
    把一个子任务分配给专门的子代理执行。

    Args:
        subagent_type: 子代理类型。可选值:
            - research：联网搜索、抓取网页（查 GitHub/文档/新闻等）
            - coder：读写文件、代码分析和修改
            - executor：执行 bash 命令
        description: 一句话说明这个任务做什么（用于日志）
        prompt: 给子代理的完整任务描述，越详细越好
    """
    from choreo.agents.sub_agents.registry import get_subagent_config, list_subagents
    from choreo.agents.sub_agents.executor import SubagentExecutor
    from langgraph.config import get_config, get_stream_writer

    config = get_subagent_config(subagent_type)
    if config is None:
        available = ", ".join(list_subagents())
        return f"未知子代理类型: {subagent_type!r}。可用类型: {available}"

    parent_config = get_config()
    thread_id = (parent_config.get("configurable") or {}).get("thread_id", "unknown")
    model_name = (parent_config.get("configurable") or {}).get("model_name")

    task_id = str(uuid.uuid4())[:8]

    try:
        stream_writer = get_stream_writer()
    except RuntimeError:
        stream_writer = None

    logger.info(
        "task tool: dispatching %r to sub-agent[%s], thread=%s, task_id=%s",
        description, subagent_type, thread_id, task_id,
    )

    if stream_writer:
        stream_writer({
            "subagent_event": {
                "task_id": task_id,
                "subagent_type": subagent_type,
                "event_type": "start",
                "description": description,
            }
        })

    executor = SubagentExecutor(
        config=config,
        all_tools=_get_all_tools(),
        parent_model_name=model_name,
    )
    return await executor.aexecute(
        prompt,
        thread_id=thread_id,
        task_id=task_id,
        stream_writer=stream_writer,
    )
