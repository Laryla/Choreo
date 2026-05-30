"""McpContextMiddleware：在每次 LLM 调用前将紧凑 MCP 工具目录追加到 system prompt。

只显示 approval != deny 且 enabled=true 的工具名和描述，
不注入完整 JSON schema，避免 context 膨胀。
"""
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage
from choreo.mcp import get_mcp_manager


class McpContextMiddleware(AgentMiddleware):
    """在每次 LLM 调用前将紧凑 MCP 工具目录追加到 system prompt。

    只显示 approval != deny 且 enabled=true 的工具名和描述，
    不注入完整 JSON schema，避免 context 膨胀。
    """

    async def awrap_model_call(self, request, handler):
        try:
            index = await get_mcp_manager().get_index()
        except RuntimeError:
            return await handler(request)

        if index:
            existing = request.system_message.content if request.system_message else ""
            new_content = f"{existing}\n\n{index}" if existing else index
            request = request.override(
                system_message=SystemMessage(content=new_content)
            )
        return await handler(request)
