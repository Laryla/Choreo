"""McpApprovalMiddleware：在 LangGraph 层拦截 mcp_call 工具调用，处理 confirm 审批。

只处理 approval=confirm 的情况（触发 HITL interrupt）。
approval=deny 由 MCP 层的 deny_interceptor 处理。
approval=auto 两层都放行。
"""
from langchain.agents.middleware import AgentMiddleware
from langgraph.types import interrupt


class McpApprovalMiddleware(AgentMiddleware):
    """在 LangGraph 层拦截 mcp_call 工具调用，处理 confirm 审批。

    只处理 approval=confirm 的情况（触发 HITL interrupt）。
    approval=deny 由 MCP 层的 deny_interceptor 处理。
    approval=auto 两层都放行。
    """

    async def awrap_tool_call(self, request, handler):
        if request.tool_call["name"] != "mcp_call":
            return await handler(request)

        args = request.tool_call.get("args", {})
        server = args.get("server", "")
        tool_name = args.get("tool", "")
        arguments = args.get("arguments", {})
        tool_call_id = request.tool_call.get("id", "")

        approval = await _get_approval(server, tool_name)

        if approval == "confirm":
            decision = interrupt({
                "action_requests": [{
                    "name": f"{server} · {tool_name}",
                    "arguments": arguments,
                }],
                "review_configs": [{
                    "action_name": f"{server} · {tool_name}",
                    "allowed_decisions": ["approve", "reject"],
                }],
            })
            decisions = (decision or {}).get("decisions", [])
            if decisions and decisions[0].get("type") == "reject":
                from langchain_core.messages import ToolMessage
                return ToolMessage(
                    content=f"Tool '{server}/{tool_name}' was rejected by user.",
                    tool_call_id=tool_call_id,
                )

        # approval=auto 或 confirm 批准后：放行执行
        return await handler(request)


async def _get_approval(server: str, tool: str) -> str:
    """从 DB 读取工具的 approval 配置，默认 confirm。"""
    from choreo.db import SessionLocal, McpServerRow
    try:
        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server)
            if row and row.tools_config:
                return row.tools_config.get(tool, {}).get("approval", "confirm")
    except Exception:
        pass
    return "confirm"
