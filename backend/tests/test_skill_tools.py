import pytest
import time
from unittest.mock import patch
from choreo.skills.store import LocalSkillStore
from choreo.models.skill import SkillCreate, SkillPatch


@pytest.fixture
def store(tmp_path):
    return LocalSkillStore(tmp_path / "skills")


@pytest.fixture
def mock_store(store):
    with patch("choreo.agents.tools.skill_tool.get_skill_store", return_value=store):
        yield store


@pytest.fixture
def mock_config():
    with patch("choreo.agents.tools.skill_tool.get_config", return_value={"configurable": {"thread_id": "t-123"}}):
        yield


@pytest.mark.asyncio
async def test_skill_patch_updates_content(mock_store, mock_config):
    await mock_store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history",
        content="## Steps\n1. Run git log"
    ))
    from choreo.agents.tools.skill_tool import skill_patch
    result = await skill_patch.ainvoke({"skill_id": "git/log", "content": "## Steps\n1. Run git log\n2. Filter by author"})
    assert "更新成功" in result
    skill = await mock_store.get("git/log")
    assert "Filter by author" in skill.content
    assert skill.last_reviewed_by == "t-123"


@pytest.mark.asyncio
async def test_skill_patch_rejects_builtin(mock_store, mock_config):
    await mock_store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history",
        source="builtin"
    ))
    from choreo.agents.tools.skill_tool import skill_patch
    result = await skill_patch.ainvoke({"skill_id": "git/log", "content": "hacked"})
    assert "内置技能" in result
    skill = await mock_store.get("git/log")
    assert "hacked" not in skill.content


@pytest.mark.asyncio
async def test_skill_patch_rejects_locked(mock_store, mock_config):
    await mock_store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history"
    ))
    await mock_store.update("git/log", SkillPatch(locked=True))
    from choreo.agents.tools.skill_tool import skill_patch
    result = await skill_patch.ainvoke({"skill_id": "git/log", "content": "new content"})
    assert "锁定" in result


@pytest.mark.asyncio
async def test_skill_patch_rejects_oversized_content(mock_store, mock_config):
    await mock_store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history"
    ))
    from choreo.agents.tools.skill_tool import skill_patch
    big = "x" * (15 * 1024 + 1)
    result = await skill_patch.ainvoke({"skill_id": "git/log", "content": big})
    assert "15KB" in result


@pytest.mark.asyncio
async def test_skill_create_creates_skill(mock_store, mock_config):
    from choreo.agents.tools.skill_tool import skill_create
    result = await skill_create.ainvoke({
        "category": "python", "name": "venv-setup",
        "description": "Use when setting up a virtual environment",
        "content": "## Steps\n1. Run python -m venv .venv",
    })
    assert "python/venv-setup" in result
    skill = await mock_store.get("python/venv-setup")
    assert skill is not None
    assert skill.source == "ai_review"
    assert skill.last_reviewed_by == "t-123"


@pytest.mark.asyncio
async def test_skill_create_rejects_duplicate(mock_store, mock_config):
    await mock_store.create(SkillCreate(
        category="python", name="venv-setup", description="Use when setting up venv"
    ))
    from choreo.agents.tools.skill_tool import skill_create
    result = await skill_create.ainvoke({
        "category": "python", "name": "venv-setup",
        "description": "another one", "content": "content",
    })
    assert "skill_patch" in result
