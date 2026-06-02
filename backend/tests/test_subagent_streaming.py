import pytest
from unittest.mock import MagicMock, patch


def _make_config(name="test"):
    from choreo.agents.sub_agents.config import SubagentConfig
    return SubagentConfig(
        name=name,
        description="test agent",
        system_prompt="you are a test agent",
        tools=None,
        disallowed_tools=[],
    )


def _make_executor(config=None, all_tools=None):
    from choreo.agents.sub_agents.executor import SubagentExecutor
    return SubagentExecutor(config=config or _make_config(), all_tools=all_tools or [], parent_model_name=None)


def _fake_msg(content="done", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls if tool_calls is not None else []
    return msg


# ─── happy path ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aexecute_emits_tool_call_and_done_events():
    """stream_writer receives tool_call and done subagent_events."""
    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_tool_start", "name": "bash", "run_id": "r1", "data": {"input": {"command": "echo hi"}}}
        yield {"event": "on_tool_end",   "name": "bash", "run_id": "r1", "data": {"output": "hi"}}
        yield {"event": "on_chain_end",  "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [_fake_msg("done")]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream
    written = []

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        result = await _make_executor().aexecute(
            "run echo hi", thread_id="t1", task_id="tid1", stream_writer=written.append
        )

    tool_calls = [e for e in written if e.get("subagent_event", {}).get("event_type") == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["subagent_event"]["tool_name"] == "bash"
    assert tool_calls[0]["subagent_event"]["tool_args"] == {"command": "echo hi"}

    dones = [e for e in written if e.get("subagent_event", {}).get("event_type") == "done"]
    assert len(dones) == 1
    assert result == "done"


@pytest.mark.asyncio
async def test_aexecute_emits_tool_result_event():
    """on_tool_end fires a tool_result subagent_event with content preview."""
    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_tool_end", "name": "web_search", "run_id": "r1",
               "data": {"output": "search results here"}}
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [_fake_msg("summary")]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream
    written = []

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        await _make_executor().aexecute(
            "search something", thread_id="t1", task_id="tid1", stream_writer=written.append
        )

    results = [e for e in written if e.get("subagent_event", {}).get("event_type") == "tool_result"]
    assert len(results) == 1
    assert results[0]["subagent_event"]["tool_name"] == "web_search"
    assert "search results here" in results[0]["subagent_event"]["content"]


@pytest.mark.asyncio
async def test_aexecute_without_stream_writer():
    """Backward compat: no stream_writer, still returns text result."""
    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [_fake_msg("result text")]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        result = await _make_executor().aexecute("do something", thread_id="t1")

    assert result == "result text"


@pytest.mark.asyncio
async def test_aexecute_no_stream_writer_means_no_events_written():
    """When stream_writer is None, no events are written and no crash occurs."""
    written = []

    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_tool_start", "name": "bash", "run_id": "r1", "data": {"input": {}}}
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [_fake_msg("ok")]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        result = await _make_executor().aexecute("task", thread_id="t1", task_id="id1", stream_writer=None)

    assert result == "ok"
    assert written == []  # stream_writer=None means nothing collected


# ─── edge cases ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aexecute_done_emitted_even_on_stream_exception():
    """done event must fire even if astream_events raises mid-stream."""
    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_tool_start", "name": "bash", "run_id": "r1", "data": {"input": {}}}
        raise RuntimeError("stream error")

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream
    written = []

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        with pytest.raises(RuntimeError, match="stream error"):
            await _make_executor().aexecute(
                "task", thread_id="t1", task_id="tid1", stream_writer=written.append
            )

    dones = [e for e in written if e.get("subagent_event", {}).get("event_type") == "done"]
    assert len(dones) == 1, "done must be emitted even when stream raises"


@pytest.mark.asyncio
async def test_aexecute_fallback_when_no_messages():
    """Returns fallback string when final messages list is empty."""
    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": []}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        result = await _make_executor().aexecute("task", thread_id="t1")

    assert "子代理" in result  # fallback message


@pytest.mark.asyncio
async def test_aexecute_skips_messages_with_tool_calls():
    """Result extraction skips assistant messages that still have pending tool_calls."""
    tool_call_msg = _fake_msg("intermediate", tool_calls=[MagicMock()])
    final_msg = _fake_msg("final answer", tool_calls=[])

    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [tool_call_msg, final_msg]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        result = await _make_executor().aexecute("task", thread_id="t1")

    assert result == "final answer"


@pytest.mark.asyncio
async def test_aexecute_tool_output_truncated_to_500_chars():
    """tool_result content is capped at 500 chars to avoid huge SSE payloads."""
    long_output = "x" * 1000

    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_tool_end", "name": "fetch_url", "run_id": "r1",
               "data": {"output": long_output}}
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [_fake_msg("ok")]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream
    written = []

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        await _make_executor().aexecute(
            "task", thread_id="t1", task_id="tid1", stream_writer=written.append
        )

    results = [e for e in written if e.get("subagent_event", {}).get("event_type") == "tool_result"]
    assert len(results[0]["subagent_event"]["content"]) <= 500


@pytest.mark.asyncio
async def test_aexecute_subagent_type_in_all_events():
    """All emitted events carry the correct subagent_type from config."""
    async def fake_stream(*_args, **_kw):
        del _args, _kw
        yield {"event": "on_tool_start", "name": "web_search", "run_id": "r1", "data": {"input": {}}}
        yield {"event": "on_chain_end", "name": "LangGraph", "run_id": "root",
               "data": {"output": {"messages": [_fake_msg("done")]}}}

    mock_agent = MagicMock(); mock_agent.astream_events = fake_stream
    written = []

    with patch("choreo.agents.sub_agents.executor.create_agent", return_value=mock_agent), \
         patch("choreo.agents.sub_agents.executor.load_model", return_value=MagicMock()):
        await _make_executor(_make_config("research")).aexecute(
            "task", thread_id="t1", task_id="tid1", stream_writer=written.append
        )

    for event in written:
        assert event["subagent_event"]["subagent_type"] == "research"
