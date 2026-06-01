from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from langchain.agents import create_agent
from langchain_core.tools import BaseTool

from choreo.model_factory import load_model

if TYPE_CHECKING:
    from choreo.agents.sub_agents.config import SubagentConfig

logger = logging.getLogger(__name__)


def _filter_tools(
    all_tools: list[BaseTool],
    allowlist: list[str] | None,
    denylist: list[str],
) -> list[BaseTool]:
    """Filter tools by allowlist (None = all) then remove denylist entries."""
    if allowlist is not None:
        tools = [t for t in all_tools if t.name in allowlist]
    else:
        tools = list(all_tools)
    deny_set = set(denylist)
    return [t for t in tools if t.name not in deny_set]


class SubagentExecutor:
    def __init__(
        self,
        config: SubagentConfig,
        all_tools: list[BaseTool],
        parent_model_name: str | None = None,
    ) -> None:
        self.config = config
        self.tools = _filter_tools(all_tools, config.tools, config.disallowed_tools)
        self.model_name = parent_model_name if config.model == "inherit" else config.model
        logger.debug(
            "SubagentExecutor[%s]: %d tools available, model=%s",
            config.name, len(self.tools), self.model_name,
        )

    async def aexecute(
        self,
        task: str,
        thread_id: str,
        task_id: str | None = None,
        stream_writer: Callable[[Any], None] | None = None,
    ) -> str:
        agent = create_agent(
            model=load_model(self.model_name),
            tools=self.tools,
            system_prompt=self.config.system_prompt,
        )
        sub_thread_id = f"{self.config.name}-{thread_id}"
        logger.info("Sub-agent[%s] starting, thread=%s", self.config.name, sub_thread_id)

        should_emit = stream_writer is not None and task_id is not None
        final_messages: list = []

        try:
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": task}]},
                config={"configurable": {"thread_id": sub_thread_id}},
                version="v2",
            ):
                event_type = event.get("event", "")

                if event_type == "on_tool_start":
                    if should_emit:
                        stream_writer({
                            "subagent_event": {
                                "task_id": task_id,
                                "subagent_type": self.config.name,
                                "event_type": "tool_call",
                                "tool_name": event.get("name", ""),
                                "tool_args": event.get("data", {}).get("input", {}),
                            }
                        })

                elif event_type == "on_tool_end":
                    if should_emit:
                        output = event.get("data", {}).get("output", "")
                        if hasattr(output, "content"):
                            content_str = str(output.content)
                        elif isinstance(output, str):
                            content_str = output
                        else:
                            content_str = str(output)
                        content_preview = content_str[:500]
                        stream_writer({
                            "subagent_event": {
                                "task_id": task_id,
                                "subagent_type": self.config.name,
                                "event_type": "tool_result",
                                "tool_name": event.get("name", ""),
                                "content": content_preview,
                            }
                        })

                elif event_type == "on_chain_end" and event.get("name") == "LangGraph":
                    output = event.get("data", {}).get("output", {})
                    if isinstance(output, dict):
                        final_messages = output.get("messages", [])
                    else:
                        logger.warning("Sub-agent[%s] unexpected output type: %s", self.config.name, type(output))
        finally:
            if should_emit:
                stream_writer({
                    "subagent_event": {
                        "task_id": task_id,
                        "subagent_type": self.config.name,
                        "event_type": "done",
                    }
                })

        for msg in reversed(final_messages):
            content = getattr(msg, "content", None)
            if content and not getattr(msg, "tool_calls", None):
                if isinstance(content, str) and content.strip():
                    return content
                if isinstance(content, list):
                    text = " ".join(
                        b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                    if text.strip():
                        return text.strip()

        return "子代理完成但未返回文本结果。"
