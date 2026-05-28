"""
TitleMiddleware：在 agent 完成第一轮对话后，用 LLM 异步生成会话标题并写入 thread_store。
使用 aafter_agent hook（agent 每次完成后触发），只在标题尚未设置时生效。
"""
from typing import Any
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from choreo.store.thread_store import thread_store

_PROMPT = (
    "请为以下用户请求生成一个简洁的对话标题，"
    "不超过 {max_chars} 个字，只返回标题本身，"
    "不要加引号、书名号或标点符号：\n\n{content}"
)


class TitleMiddleware(AgentMiddleware):
    def __init__(self, llm: BaseChatModel, max_chars: int = 20) -> None:
        super().__init__()
        self._llm = llm
        self._max_chars = max_chars

    async def aafter_agent(self, state: AgentState, runtime: Any) -> dict[str, Any] | None:
        # 从 runtime 取 thread_id
        thread_id: str | None = None
        if runtime:
            config = getattr(runtime, "config", {}) or {}
            thread_id = config.get("configurable", {}).get("thread_id")

        if not thread_id or await thread_store.get_title(thread_id):
            return None  # 已有标题或无法确定线程，跳过

        # 取第一条用户消息
        messages = state.get("messages", [])
        first_user = next(
            (m for m in messages if isinstance(m, HumanMessage)),
            None,
        )
        if not first_user:
            return None

        content = str(first_user.content)[:300]
        try:
            prompt = _PROMPT.format(max_chars=self._max_chars, content=content)
            resp = await self._llm.ainvoke(prompt)
            title = str(resp.content).strip().strip("「」《》\"""''")
            await thread_store.set_title(thread_id, title[:self._max_chars] or content[:self._max_chars])
        except Exception:
            # LLM 调用失败时降级：截断用户消息
            await thread_store.set_title(thread_id, content[:self._max_chars])

        return None
