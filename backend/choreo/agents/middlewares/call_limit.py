from typing import Any, NotRequired
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware


class _CallCountState(AgentState):
    _model_call_count: NotRequired[int]


class ModelCallLimitMiddleware(AgentMiddleware):
    state_schema = _CallCountState

    def __init__(self, max_calls: int = 20) -> None:
        self._max = max_calls

    def before_model(self, state: _CallCountState, runtime: Any) -> dict[str, Any] | None:
        count = state.get("_model_call_count", 0)
        if count >= self._max:
            raise RuntimeError(f"超出最大 LLM 调用次数限制（{self._max} 次）")
        return {"_model_call_count": count + 1}
