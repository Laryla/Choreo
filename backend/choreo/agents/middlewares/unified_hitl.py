from langchain.agents.middleware import HumanInTheLoopMiddleware


class UnifiedHITLMiddleware(HumanInTheLoopMiddleware):
    """所有 mcp_call / bash / send_notification 均需用户确认，无例外。"""
