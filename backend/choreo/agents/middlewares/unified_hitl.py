from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.messages import AIMessage, ToolMessage


async def _get_mcp_approval(server: str, tool: str) -> str:
    from choreo.db import SessionLocal, McpServerRow
    try:
        async with SessionLocal() as session:
            row = await session.get(McpServerRow, server)
            if row and row.tools_config:
                return row.tools_config.get(tool, {}).get("approval", "confirm")
    except Exception:
        pass
    return "confirm"


class UnifiedHITLMiddleware(HumanInTheLoopMiddleware):
    """统一处理所有工具确认，支持并行工具调用。

    在 after_model 里预处理 mcp_call：
    - deny  → 直接生成 blocked ToolMessage，跳过执行
    - auto  → 改名 mcp_call_auto，绕过 HITL 拦截直接执行
    - confirm → 保持 mcp_call，由父类 HITL 打包进统一 interrupt
    """

    async def aafter_model(self, state, runtime):
        messages = state["messages"]
        last_ai = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if not last_ai or not last_ai.tool_calls:
            return None

        blocked_msgs: list[ToolMessage] = []
        new_calls = []

        for tc in last_ai.tool_calls:
            if tc["name"] == "mcp_call":
                args = tc.get("args", {})
                approval = await _get_mcp_approval(args.get("server", ""), args.get("tool", ""))
                if approval == "deny":
                    blocked_msgs.append(ToolMessage(
                        content=f"Tool '{args.get('server')}/{args.get('tool')}' is blocked by policy.",
                        tool_call_id=tc["id"],
                        status="error",
                    ))
                    continue
                elif approval == "auto":
                    # 改名让父类 HITL 跳过（mcp_call_auto 不在 interrupt_on）
                    new_calls.append({**tc, "name": "mcp_call_auto"})
                    continue
                # confirm → 走父类正常拦截
            new_calls.append(tc)

        last_ai.tool_calls = new_calls

        # 父类处理 bash / send_notification / confirm mcp_call（统一 interrupt）
        result = self.after_model(state, runtime)

        if result is None:
            result = {"messages": [last_ai]}

        # 把 mcp_call_auto 名字改回 mcp_call（工具执行时能正确路由）
        for m in result["messages"]:
            if isinstance(m, AIMessage):
                m.tool_calls = [
                    {**tc, "name": "mcp_call"} if tc["name"] == "mcp_call_auto" else tc
                    for tc in m.tool_calls
                ]

        result["messages"].extend(blocked_msgs)
        return result
