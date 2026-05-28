from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from choreo.model_factory import load_model
from choreo.agents.tools import read_git_log, generate_script, run_script, send_notification
from choreo.agents.middlewares import ModelCallLimitMiddleware, TitleMiddleware
from choreo.config import settings

llm = load_model()


def create_choreo_agent(checkpointer):
    """用给定的 checkpointer 创建 Choreo agent（在 lifespan 中调用）。"""
    return create_agent(
        model=llm,
        tools=[read_git_log, generate_script, run_script, send_notification],
        system_prompt=(
            "你是 Choreo，一个开发自动化 Agent。帮助用户把重复的开发杂活变成自动运行的脚本。\n"
            "你有四个工具：read_git_log（读取 commit）、generate_script（生成脚本）、"
            "run_script（执行脚本）、send_notification（发送通知）。\n"
            "执行脚本和发送通知前，必须先生成脚本让用户确认。"
        ),
        middleware=[
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "run_script": {
                        "description": "即将执行脚本，请确认",
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
