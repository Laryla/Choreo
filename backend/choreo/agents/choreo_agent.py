from langchain.agents import create_agent
from langchain.agents.middleware.summarization import SummarizationMiddleware
from choreo.model_factory import load_model
from choreo.agents.tools import read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash
from choreo.agents.tools.mcp_tool import mcp_call, mcp_describe
from choreo.agents.tools.skill_tool import skill_manager
from choreo.agents.tools.task_tool import task
from choreo.agents.tools.scheduled_task_tool import create_scheduled_task, list_scheduled_tasks
from choreo.agents.tools.kb_tools import kb_grep, kb_read, kb_add_raw
from choreo.agents.prompt import build_system_prompt
from choreo.agents.middlewares import (
    ModelCallLimitMiddleware, TitleMiddleware,
    ModelSelectorMiddleware, SkillsContextMiddleware,
    McpContextMiddleware, RetryToolCallMiddleware,
    UnifiedHITLMiddleware,
)
from choreo.config import settings

llm = load_model()


def _make_compression_middleware() -> SummarizationMiddleware | None:
    if not settings.CONTEXT_COMPRESSION_ENABLED:
        return None
    return SummarizationMiddleware(
        model=llm,
        trigger=[
            ("messages", settings.CONTEXT_COMPRESSION_TRIGGER_MESSAGES),
            ("tokens", settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS),
        ],
        keep=("messages", settings.CONTEXT_COMPRESSION_KEEP_MESSAGES),
    )


def create_choreo_agent(checkpointer=None, headless: bool = False):
    """
    创建 Choreo agent。
    headless=True：无人值守模式，去掉 HITL/Title/Checkpointer，工具仅限只读+web。
    """
    from choreo.agents.tools.web_tools import web_search, fetch_url

    if headless:
        _allowed = {
            "web_search", "fetch_url",
            "read_file", "write_file", "edit_file", "list_dir", "grep",
            "read_git_log", "bash",
            "send_notification",
            "skill_manager", "mcp_call", "mcp_describe",
            "kb_grep", "kb_read", "kb_add_raw",
        }
        _all = [
            task,
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_manager,
            mcp_call, mcp_describe, web_search, fetch_url,
            kb_grep, kb_read, kb_add_raw,
        ]
        tools = [t for t in _all if t.name in _allowed]
        _compression = _make_compression_middleware()
        middleware = [
            *([_compression] if _compression else []),
            ModelSelectorMiddleware(),
            ModelCallLimitMiddleware(max_calls=settings.CHOREO_MAX_LLM_CALLS),
        ]
        return create_agent(
            model=llm,
            tools=tools,
            system_prompt=(
                "你是一个自动化定时任务执行助手，在无人值守的环境中独立运行。\n\n"
                "行为规范：\n"
                "- 不向用户提问，不等待确认；遇到歧义遵循'安全、保守、最小影响'原则自行判断，并在输出中标注所作假设\n"
                "- 严格按任务描述执行，不扩展范围；未明确授权的写操作一律不执行\n"
                "- 信息获取失败时，尝试替代方案后继续；无法完成时说明阻塞原因和已尝试的步骤，不返回空内容\n"
                "- 所有结论基于实际获取的数据，不编造；关键数据注明来源和采集时间\n"
                "- 涉及与上次结果对比时，明确列出新增、变更、删除项及关键差异，注明对比基线时间\n"
                "- 未指定时区默认 UTC，输出中标注所有时间的时区\n"
                "- 遵守被调用服务的速率限制，不泄露凭据与敏感信息"
            ),
            middleware=middleware,
        )

    return create_agent(
        model=llm,
        tools=[
            task,
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_manager,
            mcp_call, mcp_describe,
            create_scheduled_task, list_scheduled_tasks,
            kb_grep, kb_read, kb_add_raw,
        ],
        system_prompt=build_system_prompt(),
        middleware=[
            *([c] if (c := _make_compression_middleware()) else []),
            McpContextMiddleware(),
            SkillsContextMiddleware(),
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
            RetryToolCallMiddleware(max_retries=2, delay=1.0),
            TitleMiddleware(llm=llm, max_chars=20),
        ],
        checkpointer=checkpointer,
    )
