import asyncio
import logging
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


class RetryToolCallMiddleware(AgentMiddleware):
    """工具调用失败时自动重试，全部失败后以 ToolMessage 返回错误给 LLM。"""

    def __init__(self, max_retries: int = 2, delay: float = 1.0) -> None:
        self._max_retries = max_retries  # 重试次数（不含首次），总尝试 = max_retries + 1
        self._delay = delay

    async def awrap_tool_call(self, request, handler):
        tool_name = request.tool_call.get("name", "unknown")
        tool_call_id = request.tool_call.get("id", "")
        last_exc: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return await handler(request)
            except Exception as e:
                last_exc = e
                if attempt < self._max_retries:
                    logger.warning(
                        "Tool '%s' failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        tool_name, attempt + 1, self._max_retries + 1, e, self._delay,
                    )
                    await asyncio.sleep(self._delay)
                else:
                    logger.error(
                        "Tool '%s' failed after %d attempts: %s",
                        tool_name, self._max_retries + 1, e,
                    )

        return ToolMessage(
            content=(
                f"Tool '{tool_name}' failed after {self._max_retries + 1} attempts. "
                f"Last error: {last_exc}"
            ),
            tool_call_id=tool_call_id,
            status="error",
        )
