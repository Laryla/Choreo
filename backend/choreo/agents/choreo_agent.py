from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from choreo.model_factory import load_model
from choreo.agents.tools import read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash, skill_view
from choreo.agents.tools.mcp_tool import mcp_call, mcp_describe
from choreo.agents.middlewares import (
    ModelCallLimitMiddleware, TitleMiddleware,
    ModelSelectorMiddleware, SkillsContextMiddleware,
    McpContextMiddleware, McpApprovalMiddleware,
)
from choreo.config import settings

llm = load_model()


def create_choreo_agent(checkpointer):
    """用给定的 checkpointer 创建 Choreo agent（在 lifespan 中调用）。"""
    return create_agent(
        model=llm,
        tools=[
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_view,
            mcp_call, mcp_describe,
        ],
        system_prompt=(
            "你是 Choreo，一个开发自动化 Agent。帮助用户把重复的开发杂活变成自动运行的脚本。\n"
            "你有以下工具：\n"
            "- read_git_log：读取 git commit 历史\n"
            "- read_file / write_file / edit_file：读写和精确编辑文件\n"
            "- list_dir / grep：目录浏览和内容搜索\n"
            "- bash：执行 bash 命令（需用户确认）\n"
            "- send_notification：发送通知（需用户确认）\n"
            "- skill_view：读取技能库中某个技能（从 Available Skills 列表找 ID）\n"
            "- mcp_call：调用 MCP server 工具（从 Available MCP Tools 列表找 server/tool）\n"
            "- mcp_describe：查询某个 MCP 工具的完整参数 schema（不确定参数类型时先查）\n"
            "\n"
            "修改文件前先用 read_file；执行 bash 和发送通知前必须等用户确认。"
        ),
        middleware=[
            McpContextMiddleware(),     # 最外层：注入 MCP 工具目录
            SkillsContextMiddleware(),  # 注入 Skills 目录
            McpApprovalMiddleware(),    # confirm 类型 MCP 工具的 HITL
            ModelSelectorMiddleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "bash": {
                        "description": "即将执行 bash 命令，请确认",
                        "allowed_decisions": ["approve", "edit", "reject"],
                    },
                    "send_notification": {
                        "description": "即将发送通知，请确认",
                        "allowed_decisions": ["approve", "reject"],
                    },
                }
            ),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
            TitleMiddleware(llm=llm, max_chars=20),
        ],
        checkpointer=checkpointer,
    )
