import json
import pytest
from pathlib import Path
from choreo.skills.store import LocalSkillStore
from choreo.models.skill import SkillCreate, SkillPatch
from choreo.skills.bundled import sync_builtin_skills


@pytest.fixture
def store(tmp_path):
    return LocalSkillStore(tmp_path / "skills")


@pytest.mark.asyncio
async def test_usage_json_at_root_not_per_skill(store):
    """usage data lives at skills/.usage.json, NOT per-skill folder."""
    await store.create(SkillCreate(category="git", name="log",
                                   description="Use when reading git history"))
    assert (store._root / ".usage.json").exists()
    assert not (store._root / "git" / "log" / "usage.json").exists()


@pytest.mark.asyncio
async def test_skill_md_has_no_runtime_fields(store):
    """SKILL.md frontmatter must NOT contain pinned/state/source."""
    await store.create(SkillCreate(category="git", name="log",
                                   description="Use when reading git history"))
    import yaml
    text = (store._root / "git" / "log" / "SKILL.md").read_text()
    end = text.find("\n---", 3)
    fm = yaml.safe_load(text[3:end])
    assert "pinned" not in fm
    assert "state" not in fm
    assert "source" not in fm


@pytest.mark.asyncio
async def test_create_and_get(store):
    data = SkillCreate(category="git", name="weekly-report",
                       description="Use when generating weekly report",
                       tags=["git", "report"], content="## Steps\n1. run git log")
    skill = await store.create(data)
    assert skill.id == "git/weekly-report"
    assert skill.tags == ["git", "report"]
    assert skill.content == "## Steps\n1. run git log"
    assert skill.use_count == 0
    assert skill.state == "active"
    assert skill.source == "manual"

    fetched = await store.get("git/weekly-report")
    assert fetched is not None
    assert fetched.id == "git/weekly-report"


@pytest.mark.asyncio
async def test_list_active_excludes_archived(store):
    await store.create(SkillCreate(category="git", name="s1", description="Use when d1"))
    await store.create(SkillCreate(category="git", name="s2", description="Use when d2"))
    await store.update("git/s2", SkillPatch(state="archived"))

    active = await store.list_active()
    ids = [s.id for s in active]
    assert "git/s1" in ids
    assert "git/s2" not in ids


@pytest.mark.asyncio
async def test_update_content_increments_patch_count(store):
    await store.create(SkillCreate(category="deploy", name="checklist",
                                   description="Use when deploying"))
    updated = await store.update("deploy/checklist", SkillPatch(content="## New Content"))
    assert updated.content == "## New Content"
    assert updated.patch_count == 1


@pytest.mark.asyncio
async def test_record_use_increments_count(store):
    await store.create(SkillCreate(category="git", name="log",
                                   description="Use when reading git log"))
    await store.record_use("git/log")
    await store.record_use("git/log")
    skill = await store.get("git/log")
    assert skill.use_count == 2
    assert skill.last_activity_at is not None


@pytest.mark.asyncio
async def test_delete_removes_folder_and_usage_entry(store):
    await store.create(SkillCreate(category="git", name="to-del",
                                   description="Use when deleting"))
    await store.delete("git/to-del")
    assert await store.get("git/to-del") is None
    usage = await store._read_usage()
    assert "git/to-del" not in usage


@pytest.mark.asyncio
async def test_search(store):
    await store.create(SkillCreate(category="git", name="report",
                                   description="Use when making reports", tags=["report"]))
    await store.create(SkillCreate(category="deploy", name="checklist",
                                   description="Use when deploying"))
    results = await store.search("report")
    ids = [s.id for s in results]
    assert "git/report" in ids
    assert "deploy/checklist" not in ids


@pytest.mark.asyncio
async def test_build_index_groups_by_category(store):
    await store.create(SkillCreate(category="git", name="log",
                                   description="Use when reading git history"))
    await store.create(SkillCreate(category="git", name="report",
                                   description="Use when making weekly reports"))
    index = await store.build_index()
    assert "git:" in index
    assert "git/log" in index
    assert "git/report" in index


@pytest.mark.asyncio
async def test_list_files_excludes_skill_md(store):
    await store.create(SkillCreate(category="git", name="log",
                                   description="Use when reading git history"))
    (store._root / "git" / "log" / "template.md").write_text("# template")
    files = await store.list_files("git/log")
    assert "template.md" in files
    assert "SKILL.md" not in files


@pytest.mark.asyncio
async def test_sync_copies_builtin_skills(store):
    """Built-in skills are copied to skills/ on first sync."""
    builtin_dir = Path(__file__).parent.parent / "choreo" / "builtin_skills"
    if not builtin_dir.exists():
        pytest.skip("builtin_skills directory not found")

    await sync_builtin_skills(store)

    skill = await store.get("git/weekly-report")
    assert skill is not None
    assert skill.source == "builtin"
    assert (store._root / ".bundled_manifest").exists()


@pytest.mark.asyncio
async def test_sync_respects_user_modifications(store):
    """Re-syncing must not overwrite a skill marked user_modified=True."""
    builtin_dir = Path(__file__).parent.parent / "choreo" / "builtin_skills"
    if not builtin_dir.exists():
        pytest.skip("builtin_skills directory not found")

    await sync_builtin_skills(store)
    await store.update("git/weekly-report", SkillPatch(content="# My custom content"))
    await sync_builtin_skills(store)
    skill = await store.get("git/weekly-report")
    assert skill.content == "# My custom content"


@pytest.mark.asyncio
async def test_locked_field_defaults_false(store):
    skill = await store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history"
    ))
    assert skill.locked == False


@pytest.mark.asyncio
async def test_last_reviewed_fields_default_none(store):
    skill = await store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history"
    ))
    assert skill.last_reviewed_at is None
    assert skill.last_reviewed_by is None


@pytest.mark.asyncio
async def test_source_ai_review_accepted(store):
    skill = await store.create(SkillCreate(
        category="ai", name="test-skill",
        description="Use when testing",
        source="ai_review",
    ))
    assert skill.source == "ai_review"


@pytest.mark.asyncio
async def test_update_locked_persists(store):
    await store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history"
    ))
    from choreo.models.skill import SkillPatch
    await store.update("git/log", SkillPatch(locked=True))
    skill = await store.get("git/log")
    assert skill.locked is True
    # Unlock
    await store.update("git/log", SkillPatch(locked=False))
    skill = await store.get("git/log")
    assert skill.locked is False


@pytest.mark.asyncio
async def test_update_last_reviewed_fields_persist(store):
    await store.create(SkillCreate(
        category="git", name="log", description="Use when reading git history"
    ))
    from choreo.models.skill import SkillPatch
    import time
    now = int(time.time())
    await store.update("git/log", SkillPatch(
        last_reviewed_at=now,
        last_reviewed_by="thread-abc",
    ))
    skill = await store.get("git/log")
    assert skill.last_reviewed_at == now
    assert skill.last_reviewed_by == "thread-abc"
