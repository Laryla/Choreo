from langchain.agents import create_agent
from choreo.model_factory import load_model
from choreo.agents.tools import read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash, skill_view
from choreo.agents.tools.mcp_tool import mcp_call, mcp_describe
from choreo.agents.tools.skill_tool import skill_patch, skill_create
from choreo.agents.tools.task_tool import task
from choreo.agents.prompt import build_system_prompt
from choreo.agents.middlewares import (
    ModelCallLimitMiddleware, TitleMiddleware,
    ModelSelectorMiddleware, SkillsContextMiddleware,
    McpContextMiddleware, RetryToolCallMiddleware,
    UnifiedHITLMiddleware,
)
from choreo.config import settings

llm = load_model()


def create_choreo_agent(checkpointer):
    """用给定的 checkpointer 创建 Choreo agent（在 lifespan 中调用）。"""
    return create_agent(
        model=llm,
        tools=[
            task,
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_view,
            skill_patch, skill_create,
            mcp_call, mcp_describe,
        ],
        system_prompt=build_system_prompt(),
        middleware=[
            McpContextMiddleware(),     # 最外层：注入 MCP 工具目录
            SkillsContextMiddleware(),  # 注入 Skills 目录
            ModelSelectorMiddleware(),
            UnifiedHITLMiddleware(
                interrupt_on={
                    "bash": {
                        "description": "即将执行 bash 命令，请确认",
                        "allowed_decisions": ["approve", "edit", "reject"],
                    },
                    "send_notification": {
                        "description": "即将发送通知，请确认",
                        "allowed_decisions": ["approve", "reject"],
                    },
                    "mcp_call": {
                        "description": "即将调用 MCP 工具，请确认",
                        "allowed_decisions": ["approve", "reject"],
                    },
                }
            ),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
            RetryToolCallMiddleware(max_retries=2, delay=1.0),  # 最内层：重试实际执行
            TitleMiddleware(llm=llm, max_chars=20),
        ],
        checkpointer=checkpointer,
    )
