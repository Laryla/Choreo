# Skill CRUD Implementation Plan (Plan 1/2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现技能系统的存储层、内置技能同步、REST API、前端管理页面和 skill_view 工具。

**Architecture:** 技能统一存储在 `skills/{category}/{name}/SKILL.md`；所有运行时状态（pinned、state、use_count 等）集中在根目录 `skills/.usage.json`；内置技能放在 `choreo/builtin_skills/` 随代码发布，启动时用 `.bundled_manifest` 增量 copy 到 `skills/`，尊重用户修改。

**Tech Stack:** FastAPI, Pydantic v2, PyYAML (已有), asyncio.Lock, React, TypeScript, Tailwind, SWR, react-markdown (已有)

---

## File Map

**New files (backend):**
- `choreo/models/skill.py` — Pydantic: Skill, SkillCreate, SkillPatch
- `choreo/skills/__init__.py` — get_skill_store / set_skill_store singleton
- `choreo/skills/store.py` — LocalSkillStore (file I/O + root .usage.json)
- `choreo/skills/bundled.py` — sync_builtin_skills() startup helper
- `choreo/builtin_skills/git/weekly-report/SKILL.md` — example built-in skill
- `choreo/gateway/routers/skills.py` — REST API router
- `choreo/agents/tools/skill_tool.py` — skill_view @tool
- `tests/test_skill_store.py` — unit tests

**New files (frontend):**
- `src/api/skills.ts`
- `src/components/Skills/SkillCard.tsx`
- `src/components/Skills/SkillEditor.tsx`
- `src/pages/SkillsPage.tsx`

**Modified files:**
- `choreo/agents/tools/__init__.py` — export skill_view
- `choreo/agents/choreo_agent.py` — add skill_view to tools + update system_prompt
- `choreo/gateway/app.py` — init store + sync builtins + register router
- `config.yaml` — add `skills_dir: ./skills`
- `config.example.yaml` — add `skills_dir: ./skills`
- `frontend/src/App.tsx` — add /skills route
- `frontend/src/components/Sidebar/Sidebar.tsx` — add nav item

---

## Task 1: Pydantic Models

**Files:**
- Create: `backend/choreo/models/skill.py`

- [ ] **Step 1: Create the models file**

```python
# backend/choreo/models/skill.py
from pydantic import BaseModel
from typing import Literal


class SkillCreate(BaseModel):
    category: str                              # folder name, e.g. "git"
    name: str                                  # folder name, e.g. "weekly-report"
    description: str                           # starts with "Use when..."
    version: str = "1.0.0"
    author: str = "user"
    tags: list[str] = []
    content: str = ""                          # Markdown body (no frontmatter)
    source: Literal["manual", "auto", "builtin"] = "manual"


class SkillPatch(BaseModel):
    description: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    content: str | None = None
    pinned: bool | None = None
    state: Literal["active", "archived"] | None = None


class Skill(BaseModel):
    id: str                                    # "{category}/{name}"
    category: str
    name: str
    description: str
    version: str
    author: str
    tags: list[str]
    content: str                               # Markdown body
    # From .usage.json
    source: Literal["manual", "auto", "builtin"]
    state: Literal["active", "stale", "archived"]
    pinned: bool
    use_count: int
    view_count: int
    patch_count: int
    last_activity_at: int | None
```

- [ ] **Step 2: Verify import**

```bash
cd backend && uv run python -c "from choreo.models.skill import Skill, SkillCreate, SkillPatch; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/choreo/models/skill.py
git commit -m "feat(skills): add Skill Pydantic models"
```

---

## Task 2: LocalSkillStore

**Files:**
- Create: `backend/choreo/skills/__init__.py`
- Create: `backend/choreo/skills/store.py`
- Create: `backend/tests/test_skill_store.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_skill_store.py
import json
import pytest
from pathlib import Path
from choreo.skills.store import LocalSkillStore
from choreo.models.skill import SkillCreate, SkillPatch


@pytest.fixture
def store(tmp_path):
    return LocalSkillStore(tmp_path / "skills")


# ── Storage layout ──────────────────────────────────────────────────

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


# ── CRUD ────────────────────────────────────────────────────────────

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
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd backend && uv run pytest tests/test_skill_store.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError: No module named 'choreo.skills'`

- [ ] **Step 3: Create `choreo/skills/__init__.py`**

```python
# backend/choreo/skills/__init__.py
from __future__ import annotations
from choreo.skills.store import LocalSkillStore

_store: LocalSkillStore | None = None


def get_skill_store() -> LocalSkillStore:
    global _store
    if _store is None:
        raise RuntimeError("SkillStore not initialized. Call set_skill_store() in lifespan.")
    return _store


def set_skill_store(store: LocalSkillStore) -> None:
    global _store
    _store = store


__all__ = ["LocalSkillStore", "get_skill_store", "set_skill_store"]
```

- [ ] **Step 4: Create `choreo/skills/store.py`**

```python
# backend/choreo/skills/store.py
import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Any

import yaml

from choreo.models.skill import Skill, SkillCreate, SkillPatch

_EXCLUDED_FILES = {"SKILL.md"}
_DEFAULT_USAGE: dict[str, Any] = {
    "use_count": 0,
    "view_count": 0,
    "patch_count": 0,
    "last_activity_at": None,
    "state": "active",
    "pinned": False,
    "source": "manual",
}


def _parse_skill_md(text: str) -> tuple[dict, str]:
    """Split SKILL.md into (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    body = text[end:].lstrip("-").lstrip("\n").strip()
    return fm, body


def _write_skill_md(fm: dict, body: str) -> str:
    fm_text = yaml.dump(fm, allow_unicode=True, default_flow_style=False).rstrip()
    return f"---\n{fm_text}\n---\n\n{body}"


class LocalSkillStore:
    def __init__(self, skills_dir: str | Path) -> None:
        self._root = Path(skills_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._usage_lock = asyncio.Lock()

    @property
    def _usage_path(self) -> Path:
        return self._root / ".usage.json"

    async def _read_usage(self) -> dict:
        if not self._usage_path.exists():
            return {}
        def _read() -> dict:
            return json.loads(self._usage_path.read_text(encoding="utf-8"))
        return await asyncio.to_thread(_read)

    async def _write_usage(self, data: dict) -> None:
        def _write() -> None:
            self._usage_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        await asyncio.to_thread(_write)

    def _parse_dir(self, skill_dir: Path, usage_entry: dict) -> Skill | None:
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            return None
        fm, body = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
        if not fm.get("description"):
            return None
        u = {**_DEFAULT_USAGE, **usage_entry}
        return Skill(
            id=f"{skill_dir.parent.name}/{skill_dir.name}",
            category=skill_dir.parent.name,
            name=skill_dir.name,
            description=fm.get("description", ""),
            version=fm.get("version", "1.0.0"),
            author=fm.get("author", "user"),
            tags=fm.get("tags") or [],
            content=body,
            source=u["source"],
            state=u["state"],
            pinned=bool(u["pinned"]),
            use_count=int(u["use_count"]),
            view_count=int(u["view_count"]),
            patch_count=int(u["patch_count"]),
            last_activity_at=u["last_activity_at"],
        )

    async def list_active(self) -> list[Skill]:
        usage = await self._read_usage()
        skills = []
        for skill_md in self._root.glob("*/*/SKILL.md"):
            skill_id = f"{skill_md.parent.parent.name}/{skill_md.parent.name}"
            entry = usage.get(skill_id, {})
            if entry.get("state", "active") == "archived":
                continue
            skill = await asyncio.to_thread(self._parse_dir, skill_md.parent, entry)
            if skill:
                skills.append(skill)
        skills.sort(key=lambda s: (-int(s.pinned), -(s.last_activity_at or 0)))
        return skills

    async def list_all(self, state: str | None = None) -> list[Skill]:
        usage = await self._read_usage()
        skills = []
        for skill_md in self._root.glob("*/*/SKILL.md"):
            skill_id = f"{skill_md.parent.parent.name}/{skill_md.parent.name}"
            entry = usage.get(skill_id, {})
            if state and entry.get("state", "active") != state:
                continue
            skill = await asyncio.to_thread(self._parse_dir, skill_md.parent, entry)
            if skill:
                skills.append(skill)
        skills.sort(key=lambda s: (-int(s.pinned), -(s.last_activity_at or 0)))
        return skills

    async def search(self, q: str) -> list[Skill]:
        q_lower = q.lower()
        result = []
        for skill in await self.list_active():
            if (q_lower in skill.name.lower()
                    or q_lower in skill.description.lower()
                    or any(q_lower in t.lower() for t in skill.tags)
                    or q_lower in skill.content.lower()):
                result.append(skill)
        return result

    async def build_index(self) -> str:
        """Compact index grouped by category for system prompt injection."""
        skills = await self.list_active()
        if not skills:
            return ""
        by_cat: dict[str, list[Skill]] = {}
        for s in skills:
            by_cat.setdefault(s.category, []).append(s)
        lines = ["Available Skills (use skill_view to read full content):"]
        for cat in sorted(by_cat):
            lines.append(f"\n{cat}:")
            for s in sorted(by_cat[cat], key=lambda x: x.name):
                pin = "📌 " if s.pinned else "  "
                lines.append(f"  {pin}{s.id}: {s.description[:120]}")
        return "\n".join(lines)

    async def get(self, skill_id: str) -> Skill | None:
        parts = skill_id.split("/", 1)
        if len(parts) != 2:
            return None
        skill_dir = self._root / parts[0] / parts[1]
        usage = await self._read_usage()
        entry = usage.get(skill_id, {})
        return await asyncio.to_thread(self._parse_dir, skill_dir, entry)

    async def list_files(self, skill_id: str) -> list[str]:
        parts = skill_id.split("/", 1)
        if len(parts) != 2:
            return []
        skill_dir = self._root / parts[0] / parts[1]
        if not skill_dir.exists():
            return []
        return sorted(
            f.name for f in skill_dir.iterdir()
            if f.is_file() and f.name not in _EXCLUDED_FILES
        )

    async def create(self, data: SkillCreate) -> Skill:
        skill_dir = self._root / data.category / data.name
        skill_dir.mkdir(parents=True, exist_ok=True)
        fm = {
            "name": data.name,
            "description": data.description,
            "version": data.version,
            "author": data.author,
            "tags": data.tags,
        }
        skill_md_path = skill_dir / "SKILL.md"
        await asyncio.to_thread(
            skill_md_path.write_text, _write_skill_md(fm, data.content), "utf-8"
        )
        skill_id = f"{data.category}/{data.name}"
        async with self._usage_lock:
            usage = await self._read_usage()
            usage[skill_id] = {
                **_DEFAULT_USAGE,
                "source": data.source,
                "last_activity_at": int(time.time()),
            }
            await self._write_usage(usage)
        result = await self.get(skill_id)
        assert result is not None
        return result

    async def update(self, skill_id: str, patch: SkillPatch) -> Skill:
        skill = await self.get(skill_id)
        if skill is None:
            raise FileNotFoundError(f"Skill not found: {skill_id}")
        parts = skill_id.split("/", 1)
        skill_dir = self._root / parts[0] / parts[1]
        fm = {
            "name": skill.name,
            "description": patch.description if patch.description is not None else skill.description,
            "version": patch.version if patch.version is not None else skill.version,
            "author": skill.author,
            "tags": patch.tags if patch.tags is not None else skill.tags,
        }
        body = patch.content if patch.content is not None else skill.content
        await asyncio.to_thread(
            (skill_dir / "SKILL.md").write_text, _write_skill_md(fm, body), "utf-8"
        )
        async with self._usage_lock:
            usage = await self._read_usage()
            entry = usage.setdefault(skill_id, dict(_DEFAULT_USAGE))
            if patch.pinned is not None:
                entry["pinned"] = patch.pinned
            if patch.state is not None:
                entry["state"] = patch.state
            if patch.content is not None or patch.description is not None:
                entry["patch_count"] = entry.get("patch_count", 0) + 1
            entry["last_activity_at"] = int(time.time())
            # Mark builtin as user_modified in .bundled_manifest
            manifest_path = self._root / ".bundled_manifest"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if skill_id in manifest and not manifest[skill_id].get("user_modified"):
                    manifest[skill_id]["user_modified"] = True
                    await asyncio.to_thread(
                        manifest_path.write_text,
                        json.dumps(manifest, indent=2),
                        "utf-8",
                    )
            await self._write_usage(usage)
        result = await self.get(skill_id)
        assert result is not None
        return result

    async def record_use(self, skill_id: str) -> None:
        async with self._usage_lock:
            usage = await self._read_usage()
            entry = usage.setdefault(skill_id, dict(_DEFAULT_USAGE))
            entry["use_count"] = entry.get("use_count", 0) + 1
            entry["last_activity_at"] = int(time.time())
            await self._write_usage(usage)

    async def delete(self, skill_id: str) -> None:
        parts = skill_id.split("/", 1)
        if len(parts) != 2:
            return
        skill_dir = self._root / parts[0] / parts[1]
        if skill_dir.exists():
            await asyncio.to_thread(shutil.rmtree, skill_dir)
        async with self._usage_lock:
            usage = await self._read_usage()
            usage.pop(skill_id, None)
            await self._write_usage(usage)
```

- [ ] **Step 5: Run tests and verify all pass**

```bash
cd backend && uv run pytest tests/test_skill_store.py -v
```

Expected: `9 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/skills/ backend/tests/test_skill_store.py
git commit -m "feat(skills): add LocalSkillStore with root .usage.json"
```

---

## Task 3: Built-in Skills Sync

**Files:**
- Create: `backend/choreo/skills/bundled.py`
- Create: `backend/choreo/builtin_skills/git/weekly-report/SKILL.md`

- [ ] **Step 1: Create example built-in skill**

```bash
mkdir -p backend/choreo/builtin_skills/git/weekly-report
```

```markdown
<!-- backend/choreo/builtin_skills/git/weekly-report/SKILL.md -->
---
name: weekly-report
description: Use when user wants to generate a weekly git commit summary report
version: 1.0.0
author: choreo
tags:
  - git
  - report
---

## When to Use
- User asks for weekly or periodic commit summaries
- Counter-trigger: do NOT use for individual commit messages

## Steps
1. Use `read_git_log` to get commits from the last 7 days
2. Group commits by type: feat / fix / chore / docs
3. Format as a Markdown bullet list
4. Optionally send via `send_notification`

## Common Pitfalls
- Check the date range — default is 7 days but user may specify differently
- Verify the repository path before reading

## Verification Checklist
- [ ] Commit count looks reasonable for the timeframe
- [ ] All commit types are represented
```

- [ ] **Step 2: Write failing test for bundled sync**

Append to `backend/tests/test_skill_store.py`:

```python
from choreo.skills.bundled import sync_builtin_skills
from pathlib import Path


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
    # User modifies the builtin skill
    await store.update("git/weekly-report", SkillPatch(content="# My custom content"))

    # Sync again — must not overwrite
    await sync_builtin_skills(store)
    skill = await store.get("git/weekly-report")
    assert skill.content == "# My custom content"
```

- [ ] **Step 3: Run tests to confirm failure**

```bash
cd backend && uv run pytest tests/test_skill_store.py::test_sync_copies_builtin_skills -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name 'sync_builtin_skills'`

- [ ] **Step 4: Create `choreo/skills/bundled.py`**

```python
# backend/choreo/skills/bundled.py
"""
sync_builtin_skills: copy built-in skills from choreo/builtin_skills/ to skills/
on application startup, respecting user modifications tracked in .bundled_manifest.
"""
import json
import shutil
import time
from pathlib import Path

from choreo.skills.store import LocalSkillStore, _parse_skill_md

_BUILTIN_DIR = Path(__file__).parent.parent / "builtin_skills"


async def sync_builtin_skills(store: LocalSkillStore) -> None:
    """
    Idempotent sync of built-in skills to the user's skills directory.

    Logic per built-in skill:
    - Not in manifest (first run) → copy + add to .usage.json as source=builtin
    - In manifest with user_modified=False → copy (overwrite with latest version)
    - In manifest with user_modified=True → skip (respect user changes)
    """
    if not _BUILTIN_DIR.exists():
        return

    manifest_path = store._root / ".bundled_manifest"
    manifest: dict = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for skill_md in sorted(_BUILTIN_DIR.glob("*/*/SKILL.md")):
        skill_dir = skill_md.parent
        category = skill_dir.parent.name
        name = skill_dir.name
        skill_id = f"{category}/{name}"

        fm, _ = _parse_skill_md(skill_md.read_text(encoding="utf-8"))
        bundled_version = fm.get("version", "1.0.0")

        entry = manifest.get(skill_id, {})
        user_modified = entry.get("user_modified", False)

        dest_dir = store._root / category / name
        should_copy = not dest_dir.exists() or not user_modified

        if should_copy:
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(skill_md, dest_dir / "SKILL.md")

            async with store._usage_lock:
                usage = await store._read_usage()
                if skill_id not in usage:
                    usage[skill_id] = {
                        "use_count": 0,
                        "view_count": 0,
                        "patch_count": 0,
                        "last_activity_at": int(time.time()),
                        "state": "active",
                        "pinned": False,
                        "source": "builtin",
                    }
                await store._write_usage(usage)

        manifest[skill_id] = {
            "bundled_version": bundled_version,
            "user_modified": user_modified,
        }

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 5: Run all store tests**

```bash
cd backend && uv run pytest tests/test_skill_store.py -v
```

Expected: `11 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/skills/bundled.py backend/choreo/builtin_skills/
git commit -m "feat(skills): add builtin skills sync with .bundled_manifest"
```

---

## Task 4: REST API Router

**Files:**
- Create: `backend/choreo/gateway/routers/skills.py`

- [ ] **Step 1: Create the router**

```python
# backend/choreo/gateway/routers/skills.py
from fastapi import APIRouter, HTTPException, Query
from choreo.models.skill import Skill, SkillCreate, SkillPatch
from choreo.skills import get_skill_store

router = APIRouter()


@router.get("/", response_model=list[Skill])
async def list_skills(
    q: str | None = Query(default=None),
    state: str | None = Query(default=None),
):
    store = get_skill_store()
    if q:
        return await store.search(q)
    return await store.list_all(state=state)


@router.post("/", response_model=Skill, status_code=201)
async def create_skill(body: SkillCreate):
    store = get_skill_store()
    if await store.get(f"{body.category}/{body.name}"):
        raise HTTPException(409, f"Skill '{body.category}/{body.name}' already exists")
    return await store.create(body)


@router.get("/{category}/{name}", response_model=Skill)
async def get_skill(category: str, name: str):
    store = get_skill_store()
    skill = await store.get(f"{category}/{name}")
    if not skill:
        raise HTTPException(404, "skill not found")
    return skill


@router.patch("/{category}/{name}", response_model=Skill)
async def patch_skill(category: str, name: str, body: SkillPatch):
    store = get_skill_store()
    if not await store.get(f"{category}/{name}"):
        raise HTTPException(404, "skill not found")
    return await store.update(f"{category}/{name}", body)


@router.delete("/{category}/{name}", status_code=204)
async def delete_skill(category: str, name: str):
    store = get_skill_store()
    skill = await store.get(f"{category}/{name}")
    if not skill:
        raise HTTPException(404, "skill not found")
    if skill.pinned:
        raise HTTPException(403, "skill is pinned — unpin before deleting")
    await store.delete(f"{category}/{name}")


@router.get("/{category}/{name}/files")
async def list_skill_files(category: str, name: str):
    store = get_skill_store()
    if not await store.get(f"{category}/{name}"):
        raise HTTPException(404, "skill not found")
    return {"files": await store.list_files(f"{category}/{name}")}
```

- [ ] **Step 2: Commit**

```bash
git add backend/choreo/gateway/routers/skills.py
git commit -m "feat(skills): add REST API router for skill CRUD"
```

---

## Task 5: App Integration

**Files:**
- Modify: `backend/choreo/gateway/app.py`
- Modify: `backend/config.yaml`
- Modify: `backend/config.example.yaml`

- [ ] **Step 1: Add `skills_dir` to config files**

In `backend/config.yaml`, add after the `active_sandbox:` line:
```yaml
skills_dir: ./skills
```

In `backend/config.example.yaml`, add after the `active_sandbox:` line:
```yaml
skills_dir: ./skills          # 技能文件目录（内置+用户混合）
```

- [ ] **Step 2: Update `app.py`**

Add these imports at the top of `backend/choreo/gateway/app.py`:
```python
from pathlib import Path
import yaml as _yaml
from choreo.skills import set_skill_store, LocalSkillStore
from choreo.skills.bundled import sync_builtin_skills
from choreo.gateway.routers import skills as skills_router
```

In the `lifespan` function, add **before** `await init_db()`:
```python
    # 0. 初始化 SkillStore 并同步内置技能
    _cfg_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(_cfg_path, encoding="utf-8") as _f:
        _cfg = _yaml.safe_load(_f) or {}
    _skills_root = Path(__file__).parent.parent.parent / _cfg.get("skills_dir", "./skills")
    _skill_store = LocalSkillStore(_skills_root)
    await sync_builtin_skills(_skill_store)
    set_skill_store(_skill_store)
```

After the last `app.include_router(...)` call, add:
```python
app.include_router(skills_router.router, prefix="/api/skills", tags=["skills"])
```

- [ ] **Step 3: Start backend and test end-to-end**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload --port 8000
```

Verify built-in skills were copied:
```bash
ls backend/skills/git/weekly-report/
```
Expected: `SKILL.md`

```bash
cat backend/skills/.usage.json
```
Expected: JSON with `"git/weekly-report"` entry, `"source": "builtin"`

```bash
cat backend/skills/.bundled_manifest
```
Expected: JSON with `"git/weekly-report"`, `"user_modified": false`

Test creating a skill:
```bash
curl -s -X POST http://localhost:8000/api/skills/ \
  -H "Content-Type: application/json" \
  -d '{"category":"test","name":"hello","description":"Use when testing","tags":["test"],"content":"## Steps\n1. test"}' \
  | python3 -m json.tool
```
Expected: JSON with `"id": "test/hello"`, `"source": "manual"`

- [ ] **Step 4: Commit**

```bash
git add backend/choreo/gateway/app.py backend/config.yaml backend/config.example.yaml
git commit -m "feat(skills): integrate LocalSkillStore into app lifespan, register /api/skills"
```

---

## Task 6: skill_view Tool

**Files:**
- Create: `backend/choreo/agents/tools/skill_tool.py`
- Modify: `backend/choreo/agents/tools/__init__.py`
- Modify: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: Create the tool**

```python
# backend/choreo/agents/tools/skill_tool.py
from langchain_core.tools import tool
from choreo.skills import get_skill_store


@tool
async def skill_view(skill_id: str) -> str:
    """Read the full content of a skill by its ID.

    Call this when you see a relevant skill ID in the skills index
    injected into the system prompt.

    Args:
        skill_id: Skill ID in 'category/name' format, e.g. 'git/weekly-report'

    Returns:
        Full SKILL.md content: steps, pitfalls, and verification checklist.
    """
    store = get_skill_store()
    skill = await store.get(skill_id)
    if skill is None:
        return f"Skill '{skill_id}' not found. Check the skills index for valid IDs."
    await store.record_use(skill_id)
    return f"# {skill.name}\n\n{skill.content}"
```

- [ ] **Step 2: Export from `tools/__init__.py`**

Add to `backend/choreo/agents/tools/__init__.py`:
```python
from choreo.agents.tools.skill_tool import skill_view
```
Add `"skill_view"` to `__all__`.

- [ ] **Step 3: Register in `choreo_agent.py`**

Change the import line:
```python
from choreo.agents.tools import (
    read_git_log, send_notification,
    read_file, write_file, edit_file, list_dir, grep, bash,
    skill_view,
)
```

Add `skill_view` to `tools=[...]`.

Add to `system_prompt`:
```python
"- skill_view：读取技能库中某个技能的完整内容（从系统消息的 Available Skills 列表中找到 ID 后调用）\n"
```

- [ ] **Step 4: Verify agent starts**

```bash
cd backend && uv run python -c "
from langgraph.checkpoint.memory import InMemorySaver
from choreo.skills import set_skill_store, LocalSkillStore
set_skill_store(LocalSkillStore('/tmp/test-skills'))
from choreo.agents.choreo_agent import create_choreo_agent
a = create_choreo_agent(InMemorySaver())
print('OK')
"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/agents/tools/skill_tool.py backend/choreo/agents/tools/__init__.py backend/choreo/agents/choreo_agent.py
git commit -m "feat(skills): add skill_view tool - agent reads skill by ID and records use_count"
```

---

## Task 7: Frontend API Client

**Files:**
- Create: `frontend/src/api/skills.ts`

- [ ] **Step 1: Create the file**

```typescript
// frontend/src/api/skills.ts
const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const BASE = `${API}/api/skills`;

export interface Skill {
  id: string;
  category: string;
  name: string;
  description: string;
  version: string;
  author: string;
  tags: string[];
  content: string;
  source: "manual" | "auto" | "builtin";
  state: "active" | "stale" | "archived";
  pinned: boolean;
  use_count: number;
  view_count: number;
  patch_count: number;
  last_activity_at: number | null;
}

export interface SkillCreate {
  category: string;
  name: string;
  description: string;
  version?: string;
  author?: string;
  tags?: string[];
  content?: string;
}

export interface SkillPatch {
  description?: string;
  version?: string;
  tags?: string[];
  content?: string;
  pinned?: boolean;
  state?: "active" | "archived";
}

export const getSkills = (q?: string, state?: string): Promise<Skill[]> => {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (state) p.set("state", state);
  const qs = p.toString();
  return fetch(`${BASE}/${qs ? "?" + qs : ""}`).then((r) => r.json());
};

export const createSkill = (body: SkillCreate): Promise<Skill> =>
  fetch(`${BASE}/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

export const patchSkill = (
  category: string,
  name: string,
  body: SkillPatch
): Promise<Skill> =>
  fetch(`${BASE}/${category}/${name}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const deleteSkill = (category: string, name: string): Promise<void> =>
  fetch(`${BASE}/${category}/${name}`, { method: "DELETE" }).then(() => undefined);
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/skills.ts
git commit -m "feat(skills): add frontend API client"
```

---

## Task 8: SkillCard Component

**Files:**
- Create: `frontend/src/components/Skills/SkillCard.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/Skills/SkillCard.tsx
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Skill, SkillPatch } from "@/api/skills";
import { patchSkill, deleteSkill } from "@/api/skills";

interface Props {
  skill: Skill;
  onUpdate: () => void;
  onDelete: () => void;
  onEdit: (skill: Skill) => void;
}

export default function SkillCard({ skill, onUpdate, onDelete, onEdit }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const patch = async (body: SkillPatch) => {
    setBusy(true);
    try { await patchSkill(skill.category, skill.name, body); onUpdate(); }
    finally { setBusy(false); }
  };

  const remove = async () => {
    if (!confirm(`删除技能 ${skill.id}？此操作不可撤销。`)) return;
    setBusy(true);
    try { await deleteSkill(skill.category, skill.name); onDelete(); }
    finally { setBusy(false); }
  };

  const sourceLabel: Record<string, string> = {
    auto: "自动", builtin: "内置", manual: "",
  };
  const sourceBadge: Record<string, string> = {
    auto: "bg-[#f0fdf4] dark:bg-[#0d1f12] text-[#16a34a] dark:text-[#4ade80] border-[#bbf7d0] dark:border-[#14532d]",
    builtin: "bg-[#eff6ff] dark:bg-[#0c1a2e] text-[#3b82f6] dark:text-[#60a5fa] border-[#bfdbfe] dark:border-[#1e3a5f]",
  };

  return (
    <div className={`rounded-xl border bg-white dark:bg-[#1a1a1a] ${skill.pinned ? "border-[#e2b714] dark:border-[#a38200]" : "border-[#e5e1d8] dark:border-[#252525]"}`}>
      {/* Header */}
      <div className="flex items-start gap-2 px-4 py-3 cursor-pointer select-none" onClick={() => setExpanded(e => !e)}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap mb-1">
            {skill.pinned && <span className="text-[#e2b714]">📌</span>}
            <span className="font-mono text-[12px] font-semibold text-[#1e293b] dark:text-[#c8c8c8]">{skill.id}</span>
            {skill.source !== "manual" && (
              <span className={`px-1.5 py-0.5 rounded-full text-[10px] border ${sourceBadge[skill.source] ?? ""}`}>
                {sourceLabel[skill.source]}
              </span>
            )}
            {skill.tags.map(t => (
              <span key={t} className="px-1.5 py-0.5 rounded-full text-[10px] bg-[#f5f2eb] dark:bg-[#222] text-[#666] dark:text-[#888]">#{t}</span>
            ))}
          </div>
          <p className="text-[11.5px] text-[#555] dark:text-[#888] line-clamp-1">{skill.description}</p>
          {skill.use_count > 0 && (
            <p className="text-[10px] text-[#bbb] dark:text-[#555] mt-0.5">
              调用 {skill.use_count} 次{skill.last_activity_at ? ` · ${new Date(skill.last_activity_at * 1000).toLocaleDateString("zh-CN")}` : ""}
            </p>
          )}
        </div>
        <svg className={`w-3.5 h-3.5 text-[#aaa] flex-shrink-0 mt-1 transition-transform ${expanded ? "rotate-90" : ""}`} viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 2l4 4-4 4" />
        </svg>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-3 border-t border-[#f0ede6] dark:border-[#222] pt-3">
          <div className="prose prose-sm dark:prose-invert max-w-none text-[12px] leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{skill.content || "_（无内容）_"}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-1 px-4 py-2 border-t border-[#f0ede6] dark:border-[#222]">
        <button onClick={() => patch({ pinned: !skill.pinned })} disabled={busy}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-[#e2b714] hover:bg-[#fef9c3] dark:hover:bg-[#1c1900] transition-colors disabled:opacity-40">
          {skill.pinned ? "取消锁定" : "锁定"}
        </button>
        <button onClick={() => onEdit(skill)} disabled={busy}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-[#1e293b] dark:hover:text-[#c8c8c8] hover:bg-[#f0ede6] dark:hover:bg-[#252525] transition-colors disabled:opacity-40">
          编辑
        </button>
        <button onClick={() => patch({ state: skill.state === "active" ? "archived" : "active" })} disabled={busy}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-[#555] hover:bg-[#f0ede6] dark:hover:bg-[#252525] transition-colors disabled:opacity-40">
          {skill.state === "active" ? "归档" : "恢复"}
        </button>
        <button onClick={remove} disabled={busy || skill.pinned}
          className="text-[11px] px-2 py-1 rounded-md text-[#888] hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950 transition-colors disabled:opacity-40 ml-auto">
          删除
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Skills/SkillCard.tsx
git commit -m "feat(skills): add SkillCard component"
```

---

## Task 9: SkillEditor Component

**Files:**
- Create: `frontend/src/components/Skills/SkillEditor.tsx`

- [ ] **Step 1: Create the split-pane editor**

```tsx
// frontend/src/components/Skills/SkillEditor.tsx
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Skill, SkillCreate, SkillPatch } from "@/api/skills";
import { createSkill, patchSkill } from "@/api/skills";

interface Props {
  skill?: Skill | null;   // null = create mode
  onSave: () => void;
  onClose: () => void;
}

const TEMPLATE = `## When to Use
- 

## Steps
1. 

## Common Pitfalls
- 

## Verification Checklist
- [ ] `;

export default function SkillEditor({ skill, onSave, onClose }: Props) {
  const isCreate = !skill;
  const [category, setCategory] = useState(skill?.category ?? "");
  const [name, setName] = useState(skill?.name ?? "");
  const [description, setDescription] = useState(skill?.description ?? "");
  const [tags, setTags] = useState((skill?.tags ?? []).join(", "));
  const [content, setContent] = useState(skill?.content ?? TEMPLATE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const save = async () => {
    if (!description.trim()) { setError("description 不能为空"); return; }
    if (isCreate && (!category.trim() || !name.trim())) { setError("category 和 name 不能为空"); return; }
    setBusy(true); setError("");
    try {
      const tagsArr = tags.split(",").map(t => t.trim()).filter(Boolean);
      if (isCreate) {
        await createSkill({ category: category.trim(), name: name.trim(), description, tags: tagsArr, content });
      } else {
        await patchSkill(skill!.category, skill!.name, { description, tags: tagsArr, content });
      }
      onSave();
    } catch (e: any) {
      setError(e.message ?? "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-[#1a1a1a] rounded-2xl shadow-2xl w-[90vw] max-w-5xl h-[85vh] flex flex-col overflow-hidden border border-[#e5e1d8] dark:border-[#252525]">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-[#e5e1d8] dark:border-[#252525]">
          <h2 className="text-[13px] font-semibold text-[#1e293b] dark:text-[#c8c8c8]">
            {isCreate ? "新建技能" : `编辑 ${skill!.id}`}
          </h2>
          <button onClick={onClose} className="text-[#aaa] hover:text-[#555] text-lg leading-none">✕</button>
        </div>

        {/* Meta fields */}
        <div className="flex gap-2 px-5 py-2.5 border-b border-[#f0ede6] dark:border-[#222] flex-wrap">
          {isCreate && (
            <>
              <input className="field w-28" placeholder="category" value={category} onChange={e => setCategory(e.target.value)} />
              <input className="field w-40" placeholder="name (kebab-case)" value={name} onChange={e => setName(e.target.value)} />
            </>
          )}
          <input className="field flex-1 min-w-48" placeholder="description: Use when..." value={description} onChange={e => setDescription(e.target.value)} />
          <input className="field w-44" placeholder="tags: git, report" value={tags} onChange={e => setTags(e.target.value)} />
        </div>

        {/* Split pane */}
        <div className="flex-1 flex overflow-hidden">
          <textarea
            className="flex-1 p-4 font-mono text-[12px] leading-relaxed bg-[#fafaf8] dark:bg-[#141414] text-[#1a1a1a] dark:text-[#c8c8c8] border-r border-[#e5e1d8] dark:border-[#252525] resize-none focus:outline-none"
            value={content}
            onChange={e => setContent(e.target.value)}
            spellCheck={false}
          />
          <div className="flex-1 p-4 overflow-y-auto prose prose-sm dark:prose-invert max-w-none text-[12px]">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-5 py-2.5 border-t border-[#e5e1d8] dark:border-[#252525]">
          <span className={`text-[11px] ${error ? "text-red-500" : "text-[#aaa]"}`}>
            {error || "左侧编辑 · 右侧预览"}
          </span>
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-ghost">取消</button>
            <button onClick={save} disabled={busy} className="btn-primary disabled:opacity-40">
              {busy ? "保存中…" : "保存"}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        .field{@apply px-2.5 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#141414] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none focus:border-[#1e293b] dark:focus:border-[#555];}
        .btn-primary{@apply px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors;}
        .btn-ghost{@apply px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#333] text-[#555] dark:text-[#888] text-[12px] hover:bg-[#f0ede6] dark:hover:bg-[#222] transition-colors;}
      `}</style>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Skills/SkillEditor.tsx
git commit -m "feat(skills): add split-pane SkillEditor"
```

---

## Task 10: SkillsPage

**Files:**
- Create: `frontend/src/pages/SkillsPage.tsx`

- [ ] **Step 1: Create the page**

```tsx
// frontend/src/pages/SkillsPage.tsx
import { useState } from "react";
import useSWR from "swr";
import Topbar from "@/components/Topbar/Topbar";
import SkillCard from "@/components/Skills/SkillCard";
import SkillEditor from "@/components/Skills/SkillEditor";
import type { Skill } from "@/api/skills";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
type Tab = "active" | "archived";

export default function SkillsPage() {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Tab>("active");
  const [editTarget, setEditTarget] = useState<Skill | null | undefined>(undefined);

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tab === "archived") params.set("state", "archived");
  const swrKey = `/api/skills/?${params.toString()}`;

  const { data: skills = [], mutate } = useSWR<Skill[]>(
    swrKey,
    (url: string) => fetch(`${API}${url}`).then(r => r.json())
  );

  const refresh = () => mutate();
  const categories = [...new Set(skills.map(s => s.category))].sort();

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="技能库" />

      {/* Toolbar */}
      <div className="flex items-center gap-2.5 px-6 py-2.5 border-b border-[#ddd9d0] dark:border-[#202020] bg-[#f0ede6] dark:bg-[#141414]">
        <div className="flex gap-1">
          {(["active", "archived"] as Tab[]).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-lg text-[11.5px] transition-colors ${tab === t ? "bg-[#1e293b] dark:bg-[#2a2a2a] text-white" : "text-[#666] dark:text-[#888] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e]"}`}>
              {t === "active" ? "当前" : "归档"}
            </button>
          ))}
        </div>
        <input
          className="flex-1 max-w-xs px-3 py-1.5 rounded-lg border border-[#ddd9d0] dark:border-[#252525] bg-white dark:bg-[#1a1a1a] text-[12px] text-[#1a1a1a] dark:text-[#c8c8c8] focus:outline-none"
          placeholder="搜索技能…"
          value={q}
          onChange={e => setQ(e.target.value)}
        />
        <button onClick={() => setEditTarget(null)}
          className="ml-auto px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors">
          + 新建技能
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[900px] mx-auto px-6 py-5">
          {skills.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-[#bbb] dark:text-[#333] text-sm gap-2">
              <span className="text-4xl">⚡</span>
              <span>{q ? "没有匹配的技能" : "还没有技能，点击右上角新建"}</span>
            </div>
          ) : categories.map(cat => (
            <div key={cat} className="mb-6">
              <h3 className="text-[11px] font-semibold text-[#aaa] dark:text-[#555] uppercase tracking-wider mb-2 font-mono">
                {cat}/
              </h3>
              <div className="flex flex-col gap-2">
                {skills.filter(s => s.category === cat).map(skill => (
                  <SkillCard key={skill.id} skill={skill}
                    onUpdate={refresh} onDelete={refresh}
                    onEdit={s => setEditTarget(s)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {editTarget !== undefined && (
        <SkillEditor skill={editTarget} onSave={() => { refresh(); setEditTarget(undefined); }} onClose={() => setEditTarget(undefined)} />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/SkillsPage.tsx
git commit -m "feat(skills): add SkillsPage"
```

---

## Task 11: Navigation and Routing

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Sidebar/Sidebar.tsx`

- [ ] **Step 1: Add route to `App.tsx`**

Add import:
```tsx
import SkillsPage from "./pages/SkillsPage";
```

Add route after `/history`:
```tsx
<Route path="/skills" element={<SkillsPage />} />
```

- [ ] **Step 2: Add nav item to `Sidebar.tsx`**

Add to the `NAV_ITEMS` array after "历史记录":
```tsx
{
  to: "/skills",
  label: "技能库",
  icon: (
    <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 2h10v12H3z" />
      <line x1="5" y1="5" x2="11" y2="5" />
      <line x1="5" y1="8" x2="11" y2="8" />
      <line x1="5" y1="11" x2="8" y2="11" />
    </svg>
  ),
},
```

- [ ] **Step 3: Open browser and verify end-to-end**

```bash
cd frontend && pnpm dev
```

Open http://localhost:5173, click "技能库" in sidebar. Verify:
- Built-in "git/weekly-report" appears with blue "内置" badge
- Click "+ 新建技能" → split-pane editor opens
- Fill: category=`test`, name=`hello`, description=`Use when testing`, click Save
- New card appears with source=manual (no badge), use_count=0
- Click card → Markdown preview expands
- Click "锁定" → pin icon appears
- Click "归档" → card moves to 归档 tab
- Click "编辑" → editor opens with existing content, left/right panes both work
- Modify built-in skill → restart backend → modification is preserved (not overwritten)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat(skills): add /skills route and nav"
```

---

## Self-Review

**Spec coverage:**
- ✅ `skills/{category}/{name}/SKILL.md` — pure spec, no runtime fields
- ✅ `skills/.usage.json` — single root file, all runtime state
- ✅ `skills/.bundled_manifest` — tracks builtin source and user_modified
- ✅ `choreo/builtin_skills/` — shipped with code, synced on startup
- ✅ User modifications to builtins preserved across restarts
- ✅ LocalSkillStore: list, search, get, create, update, delete, record_use, build_index, list_files
- ✅ `asyncio.Lock` protecting `.usage.json` concurrent writes
- ✅ REST API: 6 endpoints, delete blocked for pinned skills
- ✅ skill_view tool: reads full content, increments use_count
- ✅ Frontend: SkillsPage, SkillCard (expand/pin/archive/delete), SkillEditor (split-pane), category grouping

**Placeholder scan:** None.

**Type consistency:** `Skill.state` (not `status`) used throughout. `source: "manual"|"auto"|"builtin"` consistent in Pydantic and TypeScript.

---

> See Plan 2: `2026-05-29-skill-middleware.md` for SkillInjectMiddleware + SkillSedimentMiddleware + skill_manage tool.
