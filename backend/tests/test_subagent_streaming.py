import asyncio
import pytest
from unittest.mock import MagicMock


@pytest.mark.asyncio
async def test_aexecute_calls_stream_writer():
    """stream_writer should be called with subagent_event on tool start."""
    from choreo.agents.sub_agents.executor import SubagentExecutor
    from choreo.agents.sub_agents.config import SubagentConfig

    config = SubagentConfig(
        name="test",
        description="test",
        system_prompt="you are a test agent",
        tools=None,
        disallowed_tools=[],
    )

    written_events = []
    stream_writer = lambda event: written_events.append(event)

    fake_msg = MagicMock()
    fake_msg.content = "done"
    fake_msg.tool_calls = []

    async def fake_astream_events(*args, **kwargs):
        yield {"event": "on_tool_start", "name": "bash", "run_id": "abc", "data": {"input": {"command": "echo hi"}}}
        yield {"event": "on_tool_end", "name": "bash", "run_id": "abc", "data": {"output": "hi"}}
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root", "data": {"output": {"messages": [fake_msg]}}}

    mock_agent = MagicMock()
    mock_agent.astream_events = fake_astream_events

    from unittest.mock import patch
    with patch("langchain.agents.create_agent", return_value=mock_agent), \
         patch("choreo.model_factory.load_model", return_value=MagicMock()):
        executor = SubagentExecutor(config=config, all_tools=[], parent_model_name=None)
        result = await executor.aexecute(
            task="run echo hi",
            thread_id="t1",
            task_id="tid1",
            stream_writer=stream_writer,
        )

    tool_call_events = [e for e in written_events if e.get("subagent_event", {}).get("event_type") == "tool_call"]
    assert len(tool_call_events) >= 1, f"Expected tool_call event, got: {written_events}"
    assert tool_call_events[0]["subagent_event"]["tool_name"] == "bash"
    done_events = [e for e in written_events if e.get("subagent_event", {}).get("event_type") == "done"]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_aexecute_without_stream_writer_works():
    """aexecute should still work when stream_writer is None (backward compat)."""
    from choreo.agents.sub_agents.executor import SubagentExecutor
    from choreo.agents.sub_agents.config import SubagentConfig

    config = SubagentConfig(
        name="test", description="test", system_prompt="test",
        tools=None, disallowed_tools=[],
    )

    fake_msg = MagicMock()
    fake_msg.content = "result text"
    fake_msg.tool_calls = []

    async def fake_astream_events(*args, **kwargs):
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root", "data": {"output": {"messages": [fake_msg]}}}

    mock_agent = MagicMock()
    mock_agent.astream_events = fake_astream_events

    from unittest.mock import patch
    with patch("langchain.agents.create_agent", return_value=mock_agent), \
         patch("choreo.model_factory.load_model", return_value=MagicMock()):
        executor = SubagentExecutor(config=config, all_tools=[], parent_model_name=None)
        result = await executor.aexecute(task="do something", thread_id="t1")

    assert result == "result text"
