import json
import pytest
from pathlib import Path
from choreo.skills.store import LocalSkillStore
from choreo.models.skill import SkillCreate, SkillPatch


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
