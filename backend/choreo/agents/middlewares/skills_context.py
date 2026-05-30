from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from choreo.skills import get_skill_store


class SkillsContextMiddleware(AgentMiddleware):
    """在每次 LLM 调用前，将当前 active skills 的索引追加到系统消息末尾。"""

    async def awrap_model_call(self, request, handler):
        index = await get_skill_store().build_index()
        if index:
            existing = request.system_message.content if request.system_message else ""
            new_content = f"{existing}\n\n{index}" if existing else index
            request = request.override(system_message=SystemMessage(content=new_content))
        return await handler(request)
