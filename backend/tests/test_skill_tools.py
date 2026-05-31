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


# ── related_skills tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skill_create_with_related_skills(mock_store, mock_config):
    """skill_create 传入 related_skills，frontmatter 和 Skill 对象都要有这个字段。"""
    from choreo.agents.tools.skill_tool import skill_create
    result = await skill_create.ainvoke({
        "category": "git", "name": "rebase-guide",
        "description": "Use when rebasing a branch onto main",
        "content": "## Steps\n1. git fetch\n2. git rebase origin/main",
        "related_skills": ["git/commit-message", "git/weekly-report"],
    })
    assert "创建成功" in result
    skill = await mock_store.get("git/rebase-guide")
    assert skill.related_skills == ["git/commit-message", "git/weekly-report"]


@pytest.mark.asyncio
async def test_skill_patch_updates_related_skills(mock_store, mock_config):
    """skill_patch 可以更新 related_skills，不影响 content。"""
    await mock_store.create(SkillCreate(
        category="git", name="rebase-guide",
        description="Use when rebasing",
        content="## Steps\n1. git rebase",
    ))
    from choreo.agents.tools.skill_tool import skill_patch
    result = await skill_patch.ainvoke({
        "skill_id": "git/rebase-guide",
        "related_skills": ["git/commit-message"],
    })
    assert "更新成功" in result
    skill = await mock_store.get("git/rebase-guide")
    assert "git/commit-message" in skill.related_skills
    assert "## Steps" in skill.content  # content untouched


@pytest.mark.asyncio
async def test_build_index_shows_see_also(mock_store):
    """build_index 在有 related_skills 的技能旁边显示 '→ see also:'。"""
    await mock_store.create(SkillCreate(
        category="git", name="rebase-guide",
        description="Use when rebasing a branch",
        content="## Steps\n1. git rebase",
        related_skills=["git/commit-message"],
    ))
    index = await mock_store.build_index()
    assert "→ see also: git/commit-message" in index


@pytest.mark.asyncio
async def test_related_skills_persisted_to_frontmatter(mock_store):
    """create 后直接读 SKILL.md 文件，确认 related_skills 写入了 frontmatter。"""
    import yaml
    from choreo.skills.store import _parse_skill_md
    await mock_store.create(SkillCreate(
        category="debug", name="trace-guide",
        description="Use when reading tracebacks",
        content="## Steps\n1. Read bottom-up",
        related_skills=["python/uv-project"],
    ))
    skill_md_path = mock_store._root / "debug" / "trace-guide" / "SKILL.md"
    assert skill_md_path.exists()
    fm, _ = _parse_skill_md(skill_md_path.read_text())
    assert fm.get("related_skills") == ["python/uv-project"]


@pytest.mark.asyncio
async def test_related_skills_cleared_on_empty_patch(mock_store):
    """SkillPatch(related_skills=[]) 显式清空，传 None 则保留原值。"""
    await mock_store.create(SkillCreate(
        category="git", name="pr-guide",
        description="Use when opening a PR",
        content="## Steps\n1. gh pr create",
        related_skills=["git/commit-message"],
    ))
    # None → preserve
    await mock_store.update("git/pr-guide", SkillPatch(related_skills=None))
    skill = await mock_store.get("git/pr-guide")
    assert skill.related_skills == ["git/commit-message"]

    # [] → clear
    await mock_store.update("git/pr-guide", SkillPatch(related_skills=[]))
    skill = await mock_store.get("git/pr-guide")
    assert skill.related_skills == []
