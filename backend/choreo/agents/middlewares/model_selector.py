"""
ModelSelectorMiddleware：从 context["model_name"] 动态切换每次调用使用的模型。
模型实例按名称缓存，避免每次重新实例化。
"""
from typing import Any
from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_config
from choreo.model_factory import load_model

_model_cache: dict[str, Any] = {}


def _get_model(name: str):
    if name not in _model_cache:
        _model_cache[name] = load_model(name)
    return _model_cache[name]


class ModelSelectorMiddleware(AgentMiddleware):
    async def awrap_model_call(self, request, handler):
        config = get_config()
        model_name: str | None = (config.get("configurable") or {}).get("model_name")
        if model_name:
            request.model = _get_model(model_name)
        return await handler(request)
