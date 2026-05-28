"""
全局 agent 注册表。
agent 实例在 FastAPI lifespan 中创建并注入，
旧模块级单例不再使用。
"""
from langchain_core.runnables import Runnable

_agent: Runnable | None = None


def set_agent(agent: Runnable) -> None:
    global _agent
    _agent = agent


def get_agent() -> Runnable:
    if _agent is None:
        raise RuntimeError("Agent 尚未初始化，请确认 FastAPI lifespan 已启动")
    return _agent
