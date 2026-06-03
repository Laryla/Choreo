"""Tests for context compression middleware integration."""
import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents.middleware.summarization import SummarizationMiddleware


def test_summarization_middleware_instantiation():
    """SummarizationMiddleware can be created with our config values."""
    from choreo.config import settings
    from choreo.model_factory import load_model

    llm = load_model()
    middleware = SummarizationMiddleware(
        model=llm,
        trigger=[
            ("messages", settings.CONTEXT_COMPRESSION_TRIGGER_MESSAGES),
            ("tokens", settings.CONTEXT_COMPRESSION_TRIGGER_TOKENS),
        ],
        keep=("messages", settings.CONTEXT_COMPRESSION_KEEP_MESSAGES),
    )
    assert middleware is not None
    assert middleware.keep == ("messages", settings.CONTEXT_COMPRESSION_KEEP_MESSAGES)


def test_no_summarize_under_threshold():
    """Middleware does not summarize when message count is below threshold."""
    from choreo.config import settings
    from choreo.model_factory import load_model

    llm = load_model()
    middleware = SummarizationMiddleware(
        model=llm,
        trigger=[("messages", 10)],
        keep=("messages", 5),
    )
    state = {"messages": [HumanMessage(content="hello"), AIMessage(content="hi")]}
    runtime = MagicMock()
    result = middleware.before_model(state, runtime)
    assert result is None


def test_summarize_triggered_by_message_count():
    """Middleware triggers when message count exceeds threshold."""
    from choreo.model_factory import load_model

    llm = load_model()
    middleware = SummarizationMiddleware(
        model=llm,
        trigger=[("messages", 3)],
        keep=("messages", 2),
    )
    messages = [
        HumanMessage(content=f"message {i}", id=f"msg-{i}") for i in range(5)
    ]
    state = {"messages": messages}
    runtime = MagicMock()

    with patch.object(middleware, "_create_summary", return_value="摘要内容"):
        result = middleware.before_model(state, runtime)

    assert result is not None
    assert "messages" in result
