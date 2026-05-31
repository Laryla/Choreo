import pytest
from langchain_core.messages import HumanMessage, AIMessage


def _make_ai_with_tool_call(tool_name: str, skill_id: str):
    return AIMessage(
        content="",
        tool_calls=[{"id": "call_1", "name": tool_name, "args": {"skill_id": skill_id}}],
    )


def test_extract_invoked_skills_empty():
    from choreo.skills.review_worker import extract_invoked_skills
    assert extract_invoked_skills([]) == []


def test_extract_invoked_skills_from_ai_message():
    from choreo.skills.review_worker import extract_invoked_skills
    msgs = [
        HumanMessage(content="help"),
        _make_ai_with_tool_call("skill_view", "git/log"),
        _make_ai_with_tool_call("skill_view", "python/venv"),
        _make_ai_with_tool_call("bash", "git/log"),  # wrong tool, should not be included
    ]
    result = extract_invoked_skills(msgs)
    assert result == ["git/log", "python/venv"]


def test_extract_invoked_skills_deduplicates():
    from choreo.skills.review_worker import extract_invoked_skills
    msgs = [
        _make_ai_with_tool_call("skill_view", "git/log"),
        _make_ai_with_tool_call("skill_view", "git/log"),
    ]
    result = extract_invoked_skills(msgs)
    assert result == ["git/log"]


@pytest.mark.asyncio
async def test_maybe_start_review_returns_true_when_unlocked():
    from choreo.skills.review_worker import maybe_start_review, _locks
    _locks.clear()

    import choreo.skills.review_worker as rw
    original = rw._run_review_with_pending

    created_tasks = []

    async def fake_run(tid, msgs, skills):
        created_tasks.append(tid)

    # Patch create_task to capture calls without actually running review
    import asyncio
    original_create_task = asyncio.create_task

    def mock_create_task(coro):
        import asyncio
        # Schedule on event loop but don't await
        return original_create_task(coro)

    rw._run_review_with_pending = fake_run

    result = await maybe_start_review("thread-x", [], [])
    assert result is True

    rw._run_review_with_pending = original
    _locks.clear()
