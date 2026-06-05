# Skill Self-Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two-path skill evolution: main agent can write skills during conversation, plus a background review worker auto-runs after each conversation to capture implicit knowledge.

**Architecture:** Extend existing `LocalSkillStore` + `skill_tool.py` with write tools (`skill_patch`, `skill_create`). Add a `review_worker.py` that fires as a background task from the SSE `finally` block. Frontend detects the `__review_started__` signal and triggers a delayed SWR revalidation. All write paths enforce `locked` and `builtin` protection at the store layer.

**Tech Stack:** Python asyncio, langchain `create_agent`, LangGraph `get_config`, FastAPI SSE, SWR, TypeScript

---

## File Map

| Action | Path |
|--------|------|
| Modify | `backend/choreo/models/skill.py` |
| Modify | `backend/choreo/skills/store.py` |
| Modify | `backend/choreo/agents/tools/skill_tool.py` |
| Create | `backend/choreo/skills/review_worker.py` |
| Modify | `backend/choreo/gateway/routers/runs.py` |
| Modify | `backend/choreo/gateway/routers/skills.py` |
| Modify | `backend/choreo/agents/choreo_agent.py` |
| Modify | `backend/config.example.yaml` |
| Modify | `backend/tests/test_skill_store.py` |
| Create | `backend/tests/test_review_worker.py` |
| Modify | `frontend/src/api/skills.ts` |
| Modify | `frontend/src/hooks/useChat.ts` |
| Modify | `frontend/src/pages/CustomizeSkillsPage.tsx` |
| Modify | `frontend/src/components/Skills/SkillCard.tsx` |

---

## Task 1: Extend Skill Models

**Files:**
- Modify: `backend/choreo/models/skill.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_skill_store.py  (add to existing file)
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
    from choreo.models.skill import SkillCreate
    skill = await store.create(SkillCreate(
        category="ai", name="test-skill",
        description="Use when testing",
        source="ai_review",
    ))
    assert skill.source == "ai_review"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_skill_store.py::test_locked_field_defaults_false -v
```

Expected: FAIL with `TypeError` or `AttributeError` (field doesn't exist yet)

- [ ] **Step 3: Extend the Skill models**

Replace entire `backend/choreo/models/skill.py` with:

```python
from pydantic import BaseModel
from typing import Literal


class SkillCreate(BaseModel):
    category: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = "user"
    tags: list[str] = []
    content: str = ""
    source: Literal["manual", "auto", "builtin", "ai_review"] = "manual"


class SkillPatch(BaseModel):
    description: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    content: str | None = None
    pinned: bool | None = None
    state: Literal["active", "archived"] | None = None
    locked: bool | None = None
    last_reviewed_at: int | None = None
    last_reviewed_by: str | None = None


class Skill(BaseModel):
    id: str
    category: str
    name: str
    description: str
    version: str
    author: str
    tags: list[str]
    content: str
    source: Literal["manual", "auto", "builtin", "ai_review"]
    state: Literal["active", "stale", "archived"]
    pinned: bool
    locked: bool
    use_count: int
    view_count: int
    patch_count: int
    last_activity_at: int | None
    last_reviewed_at: int | None
    last_reviewed_by: str | None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && uv run pytest tests/test_skill_store.py::test_locked_field_defaults_false tests/test_skill_store.py::test_last_reviewed_fields_default_none tests/test_skill_store.py::test_source_ai_review_accepted -v
```

Expected: FAIL (still need store changes — expected at this point)

- [ ] **Step 5: Update store defaults and _parse_dir**

In `backend/choreo/skills/store.py`:

Replace `_DEFAULT_USAGE` dict:

```python
_DEFAULT_USAGE: dict[str, Any] = {
    "use_count": 0,
    "view_count": 0,
    "patch_count": 0,
    "last_activity_at": None,
    "state": "active",
    "pinned": False,
    "locked": False,
    "source": "manual",
    "last_reviewed_at": None,
    "last_reviewed_by": None,
}
```

Replace the `_parse_dir` method body (the `Skill(...)` constructor call) to pass the new fields:

```python
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
            locked=bool(u.get("locked", False)),
            use_count=int(u["use_count"]),
            view_count=int(u["view_count"]),
            patch_count=int(u["patch_count"]),
            last_activity_at=u["last_activity_at"],
            last_reviewed_at=u.get("last_reviewed_at"),
            last_reviewed_by=u.get("last_reviewed_by"),
        )
```

In `store.update()`, add handling for the new patch fields inside the `async with self._usage_lock:` block. Find the section that handles `patch.pinned` and add after it:

```python
            if patch.locked is not None:
                entry["locked"] = patch.locked
            if patch.last_reviewed_at is not None:
                entry["last_reviewed_at"] = patch.last_reviewed_at
            if patch.last_reviewed_by is not None:
                entry["last_reviewed_by"] = patch.last_reviewed_by
```

- [ ] **Step 6: Run all new tests**

```bash
cd backend && uv run pytest tests/test_skill_store.py -v
```

Expected: All pass

- [ ] **Step 7: Commit**

```bash
cd backend && git add choreo/models/skill.py choreo/skills/store.py tests/test_skill_store.py
git commit -m "feat(skills): add locked, last_reviewed_at/by fields to Skill model and store"
```

---

## Task 2: Add Store Helper Methods

**Files:**
- Modify: `backend/choreo/skills/store.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_skill_store.py  (add to existing file)
@pytest.mark.asyncio
async def test_list_by_category(store):
    await store.create(SkillCreate(category="git", name="log", description="Use when reading git history"))
    await store.create(SkillCreate(category="git", name="commit", description="Use when committing"))
    await store.create(SkillCreate(category="python", name="venv", description="Use when setting up venv"))
    results = await store.list_by_category("git")
    ids = [s.id for s in results]
    assert "git/log" in ids
    assert "git/commit" in ids
    assert "python/venv" not in ids


@pytest.mark.asyncio
async def test_review_log_rolling(store):
    for i in range(105):
        await store.append_review_log({
            "thread_id": f"t{i}", "ts": i,
            "updated": [], "created": [],
        })
    entries = await store.read_review_log(limit=200)
    assert len(entries) == 100  # capped at 100


@pytest.mark.asyncio
async def test_review_log_returns_last_n(store):
    for i in range(5):
        await store.append_review_log({"thread_id": f"t{i}", "ts": i, "updated": [], "created": []})
    entries = await store.read_review_log(limit=2)
    assert len(entries) == 2
    assert entries[-1]["thread_id"] == "t4"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_skill_store.py::test_list_by_category tests/test_skill_store.py::test_review_log_rolling -v
```

Expected: FAIL with `AttributeError`

- [ ] **Step 3: Add methods to LocalSkillStore**

Add the following three methods to `LocalSkillStore` in `backend/choreo/skills/store.py`, after the `record_use` method:

```python
    @property
    def _review_log_path(self) -> Path:
        return self._root / ".review_log.jsonl"

    async def list_by_category(self, category: str) -> list[Skill]:
        """Return all active skills in a given category (for skill_create dedup)."""
        all_skills = await self.list_active()
        return [s for s in all_skills if s.category == category]

    async def append_review_log(self, entry: dict) -> None:
        """Append one review result, keeping at most 100 entries (rolling)."""
        def _write() -> None:
            lines: list[str] = []
            if self._review_log_path.exists():
                lines = self._review_log_path.read_text(encoding="utf-8").splitlines()
            lines.append(json.dumps(entry, ensure_ascii=False))
            if len(lines) > 100:
                lines = lines[-100:]
            self._review_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        await asyncio.to_thread(_write)

    async def read_review_log(self, limit: int = 10) -> list[dict]:
        """Return last `limit` review log entries."""
        def _read() -> list[dict]:
            if not self._review_log_path.exists():
                return []
            lines = self._review_log_path.read_text(encoding="utf-8").splitlines()
            tail = lines[-limit:] if limit < len(lines) else lines
            result = []
            for line in tail:
                line = line.strip()
                if line:
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return result
        return await asyncio.to_thread(_read)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_skill_store.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
cd backend && git add choreo/skills/store.py tests/test_skill_store.py
git commit -m "feat(skills): add list_by_category and rolling review_log to LocalSkillStore"
```

---

## Task 3: Add skill_patch and skill_create Agent Tools

**Files:**
- Modify: `backend/choreo/agents/tools/skill_tool.py`
- Create: `backend/tests/test_skill_tools.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_skill_tools.py
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from choreo.skills.store import LocalSkillStore
from choreo.models.skill import SkillCreate


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
    from choreo.models.skill import SkillPatch
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_skill_tools.py -v
```

Expected: FAIL with `ImportError` (skill_patch not defined yet)

- [ ] **Step 3: Implement skill_patch and skill_create**

Replace entire `backend/choreo/agents/tools/skill_tool.py`:

```python
import time
from langchain_core.tools import tool
from langgraph.config import get_config
from choreo.skills import get_skill_store
from choreo.models.skill import SkillCreate, SkillPatch

_MAX_CONTENT_BYTES = 15 * 1024  # 15 KB


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


@tool
async def skill_patch(
    skill_id: str,
    content: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update an existing skill's content or metadata.

    Only call when:
    1. User explicitly asks to record a method, preference, or convention
       (e.g. "记住这个", "把这个方法记成技能")
    2. You are confident the discovered knowledge has high reuse value for
       future similar tasks AND the current task is already complete.

    Do NOT call mid-task — the background review will handle it after the conversation.

    Args:
        skill_id: Skill ID in 'category/name' format
        content: New Markdown body (replaces existing body if provided)
        description: New one-line description
        tags: New tag list (≤ 3 items, replaces existing)

    Returns:
        Success summary or rejection reason.
    """
    store = get_skill_store()
    skill = await store.get(skill_id)
    if skill is None:
        return f"技能 '{skill_id}' 不存在，请先用 skill_create 新建。"
    if skill.source == "builtin":
        return "内置技能不可修改（source=builtin）。若需定制，请新建同名覆盖版本。"
    if skill.locked:
        return "技能已被用户锁定（locked=true），无法修改。用户可在技能面板解锁。"
    if content is not None and len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
        return "内容超过 15KB 限制，请精简后重试（当前技能应聚焦单一场景）。"

    config = get_config()
    thread_id = (config.get("configurable") or {}).get("thread_id")
    now = int(time.time())

    await store.update(skill_id, SkillPatch(
        content=content,
        description=description,
        tags=tags,
        last_reviewed_at=now,
        last_reviewed_by=thread_id,
    ))
    updated = await store.get(skill_id)
    return f"技能 '{skill_id}' 更新成功（patch_count={updated.patch_count}）。"


@tool
async def skill_create(
    category: str,
    name: str,
    description: str,
    content: str,
    tags: list[str] | None = None,
) -> str:
    """Create a new skill.

    Before calling, check the returned sibling list to avoid semantic duplicates.
    If a similar skill exists, prefer skill_patch instead.

    Only call when:
    1. User explicitly asks to record a new skill
    2. You confirmed no existing skill covers this scenario after reviewing
       the same-category list below.

    Args:
        category: Lowercase category folder name (e.g. 'git', 'python', 'deploy')
        name: kebab-case skill name (e.g. 'weekly-report', 'venv-setup')
        description: One sentence answering "Use when..." — required
        content: Markdown body with steps, pitfalls, and verification
        tags: Optional list of ≤ 3 tags

    Returns:
        New skill ID + same-category sibling list for semantic dedup confirmation,
        or conflict error if exact name already exists.
    """
    store = get_skill_store()
    skill_id = f"{category}/{name}"

    if await store.get(skill_id) is not None:
        return (
            f"技能 '{skill_id}' 已存在，请改用 skill_patch 更新内容。"
        )
    if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
        return "内容超过 15KB 限制，请精简后重试。"

    config = get_config()
    thread_id = (config.get("configurable") or {}).get("thread_id")
    now = int(time.time())

    new_skill = await store.create(SkillCreate(
        category=category,
        name=name,
        description=description,
        content=content,
        tags=tags or [],
        source="ai_review",
    ))

    await store.update(skill_id, SkillPatch(
        last_reviewed_at=now,
        last_reviewed_by=thread_id,
    ))

    # Return sibling list so caller can confirm no semantic duplicates slipped through
    siblings = await store.list_by_category(category)
    sibling_lines = "\n".join(
        f"  - {s.id}: {s.description[:80]}"
        for s in siblings if s.id != skill_id
    )
    sibling_block = f"\n同 category 现有技能（请确认无语义重复）：\n{sibling_lines}" if sibling_lines else ""

    return f"技能 '{skill_id}' 创建成功。{sibling_block}"
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_skill_tools.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
cd backend && git add choreo/agents/tools/skill_tool.py tests/test_skill_tools.py
git commit -m "feat(skills): add skill_patch and skill_create agent tools with builtin/locked/15KB guards"
```

---

## Task 4: Build Background Review Worker

**Files:**
- Create: `backend/choreo/skills/review_worker.py`
- Create: `backend/tests/test_review_worker.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_review_worker.py
import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langchain_core.messages import AIMessage


def _make_ai_with_tool_call(tool_name: str, skill_id: str):
    """Create an AIMessage that records a tool call."""
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
async def test_maybe_start_review_returns_true_when_no_lock():
    from choreo.skills.review_worker import maybe_start_review, _locks
    _locks.clear()

    started_calls = []

    async def fake_review(tid, msgs, skills):
        started_calls.append(tid)

    import choreo.skills.review_worker as rw
    original = rw._run_review_with_pending
    rw._run_review_with_pending = lambda t, m, s: None  # don't actually run

    import asyncio
    result = await maybe_start_review("thread-x", [], [])
    assert result is True

    rw._run_review_with_pending = original
    _locks.clear()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd backend && uv run pytest tests/test_review_worker.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Create review_worker.py**

Create `backend/choreo/skills/review_worker.py`:

```python
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import yaml

from choreo.skills import get_skill_store

logger = logging.getLogger(__name__)

# Per-thread concurrency state
_locks: dict[str, asyncio.Lock] = {}
_pending: dict[str, tuple[list, list[str]]] = {}


def _get_lock(thread_id: str) -> asyncio.Lock:
    if thread_id not in _locks:
        _locks[thread_id] = asyncio.Lock()
    return _locks[thread_id]


def extract_invoked_skills(messages: list) -> list[str]:
    """Deterministically extract skill_view call arguments from LangGraph message history."""
    seen: list[str] = []
    for msg in messages:
        tool_calls: Any = None
        if hasattr(msg, "tool_calls"):
            tool_calls = msg.tool_calls
        elif isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")

        if not tool_calls:
            continue

        for tc in tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name")
                args = tc.get("args", {})
            else:
                name = getattr(tc, "name", None)
                args = getattr(tc, "args", {})

            if name != "skill_view":
                continue

            skill_id = args.get("skill_id") if isinstance(args, dict) else getattr(args, "skill_id", None)
            if skill_id and skill_id not in seen:
                seen.append(skill_id)

    return seen


async def maybe_start_review(
    thread_id: str,
    messages: list,
    invoked_skills: list[str],
) -> bool:
    """Fire background review, or queue it if one is already running.

    Returns True if a new review task was started, False if queued.
    """
    lock = _get_lock(thread_id)

    if lock.locked():
        _pending[thread_id] = (messages, invoked_skills)
        return False

    asyncio.create_task(_run_review_with_pending(thread_id, messages, invoked_skills))
    return True


async def _run_review_with_pending(thread_id: str, messages: list, invoked_skills: list[str]) -> None:
    """Run review, then drain the pending slot if populated during this run."""
    lock = _get_lock(thread_id)
    async with lock:
        await _run_review(thread_id, messages, invoked_skills)

    pending = _pending.pop(thread_id, None)
    if pending:
        msgs, skills = pending
        asyncio.create_task(_run_review_with_pending(thread_id, msgs, skills))


def _load_review_model():
    from choreo.model_factory import load_model
    yaml_path = Path(__file__).parent.parent.parent / "config.yaml"
    try:
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        review_model_name = cfg.get("review_model")
    except Exception:
        review_model_name = None
    return load_model(review_model_name)


def _format_messages_for_review(messages: list) -> str:
    """Summarize conversation history for the review prompt."""
    lines = []
    for msg in messages:
        if hasattr(msg, "type"):
            role = msg.type
            content = getattr(msg, "content", "")
        elif isinstance(msg, dict):
            role = msg.get("type") or msg.get("role", "unknown")
            content = msg.get("content", "")
        else:
            continue

        if isinstance(content, list):
            text_parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = " ".join(text_parts)
        content = str(content)

        if role in ("human", "user"):
            lines.append(f"用户: {content}")
        elif role in ("ai", "assistant") and content.strip():
            lines.append(f"Agent: {content[:800]}" + ("..." if len(content) > 800 else ""))

    return "\n\n".join(lines) if lines else "（无有效对话内容）"


def _extract_review_actions(messages: list) -> tuple[list[str], list[str]]:
    """Return (updated_skill_ids, created_skill_ids) from review agent output messages."""
    updated: list[str] = []
    created: list[str] = []

    for msg in messages:
        tool_calls: Any = None
        if hasattr(msg, "tool_calls"):
            tool_calls = msg.tool_calls
        elif isinstance(msg, dict):
            tool_calls = msg.get("tool_calls")
        if not tool_calls:
            continue

        for tc in tool_calls:
            if isinstance(tc, dict):
                name, args = tc.get("name"), tc.get("args", {})
            else:
                name, args = getattr(tc, "name", None), getattr(tc, "args", {})

            if name == "skill_patch":
                sid = args.get("skill_id") if isinstance(args, dict) else getattr(args, "skill_id", None)
                if sid and sid not in updated:
                    updated.append(sid)
            elif name == "skill_create":
                cat = args.get("category") if isinstance(args, dict) else getattr(args, "category", None)
                nm = args.get("name") if isinstance(args, dict) else getattr(args, "name", None)
                if cat and nm:
                    sid = f"{cat}/{nm}"
                    if sid not in created:
                        created.append(sid)

    return updated, created


_REVIEW_SYSTEM_PROMPT = """\
你是 Choreo 的技能复盘 agent。你的核心使命是：
让 agent 在这个用户的环境和工作方式下越来越有效。

## 本次已知信息

本次对话中 agent 主动查阅了以下技能（已确认调用）：
{invoked_list}

这些技能是优先 patch 的候选。用 skill_view 读取全文后再决定是否修改。

## 三类值得记录的信息

**1. 用户的工作方式和偏好**
- 用户偏好的代码风格、提交格式、命名习惯
- 用户喜欢怎样的解释方式（详细/简洁、中文/英文）
- 用户在这个项目里遵循的约定

**2. 这个场景下有效的方法**
- 解决某类问题时哪个路径更短
- 哪些工具组合在这个项目里效果好
- agent 走了弯路后发现的更优做法

**3. 避坑信息**
- 在这个环境里踩过的坑（依赖冲突、路径问题、API 怪癖）
- 用户明确说"不要这样做"的模式
- 上一次做错的地方，这次做对了的原因

## 写入优先级（按顺序尝试）

1. patch 上方列出的已调用技能（先 skill_view 读全文，再决定改哪里）
2. patch 其他相关现有技能（需先 skill_view 确认内容再 patch）
3. 新建技能（仅当没有任何现有技能覆盖这个场景时）
   - 新建前：查看 skill_create 返回的同 category 现有列表，确认无语义重复

## 写入质量要求

- 记录的是"下次遇到类似情况，agent 应该怎么做"，而不是"这次发生了什么"
- patch 时只追加或修正，不整体重写，单次 patch 后技能总大小不超过 15KB
- 新建技能的 description 必须一句话回答"何时用这个技能"
- category 用小写英文，name 用 kebab-case，tags ≤ 3 个

## 明确不写的情况

- 内置技能（source=builtin）— 工具会拒绝
- 被锁定的技能（locked=true）— 工具会拒绝
- 纯环境错误（缺包、权限、网络）— 不是可复用的知识
- 完全一次性的任务，未来不可能遇到相同场景
- 对话内容过于简单或无实质内容（如纯问候）— 直接退出即可，无需强行写\
"""


async def _run_review(thread_id: str, messages: list, invoked_skills: list[str]) -> None:
    """Core review worker: runs a restricted stateless agent to update skills."""
    from langchain.agents import create_agent
    from choreo.agents.tools.skill_tool import skill_view, skill_patch, skill_create

    try:
        review_llm = _load_review_model()

        invoked_list = "\n".join(f"- {s}" for s in invoked_skills) if invoked_skills else "（本次无已记录调用）"
        system_prompt = _REVIEW_SYSTEM_PROMPT.format(invoked_list=invoked_list)
        history_text = _format_messages_for_review(messages)

        review_agent = create_agent(
            model=review_llm,
            tools=[skill_view, skill_patch, skill_create],
            system_prompt=system_prompt,
        )

        result = await review_agent.ainvoke(
            {"messages": [{"role": "user", "content": history_text}]},
            config={"configurable": {"thread_id": f"review-{thread_id}"}},
        )

        updated, created = _extract_review_actions(result.get("messages", []))

        store = get_skill_store()
        await store.append_review_log({
            "thread_id": thread_id,
            "ts": int(time.time()),
            "updated": updated,
            "created": created,
        })

        logger.info(
            "Review complete for %s: updated=%s created=%s", thread_id, updated, created
        )

    except Exception:
        logger.warning("Background review failed for thread %s", thread_id, exc_info=True)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_review_worker.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
cd backend && git add choreo/skills/review_worker.py tests/test_review_worker.py
git commit -m "feat(skills): add background review worker with pending_snapshot concurrency pattern"
```

---

## Task 5: Wire Review Trigger in runs.py

**Files:**
- Modify: `backend/choreo/gateway/routers/runs.py`

- [ ] **Step 1: Modify the `finally` block in `_run_agent`**

In `backend/choreo/gateway/routers/runs.py`, replace the `finally` block of `_run_agent` (lines 158–163) with:

```python
    except Exception as e:
        await queue.put({"event": "error", "data": {"message": str(e)}})
    finally:
        state = await thread_store.get(thread_id)
        if state and state.status == "running":
            await thread_store.set_status(thread_id, "idle")
        await get_sandbox_manager().release(thread_id)

        # Trigger background skill review
        review_started = False
        if run_input is not None and not isinstance(run_input, Command):
            # Only review on real user messages, not on HITL resume
            try:
                from choreo.skills.review_worker import extract_invoked_skills, maybe_start_review
                agent_state = await get_agent().aget_state(config)
                final_messages = agent_state.values.get("messages", [])
                invoked_skills = extract_invoked_skills(final_messages)
                review_started = await maybe_start_review(thread_id, final_messages, invoked_skills)
            except Exception:
                pass  # Never crash SSE over review failure

        await queue.put({"event": "updates", "data": {"__review_started__": review_started}})
        await queue.put(None)
```

- [ ] **Step 2: Manually verify SSE output format**

Start the backend and make a test request. Confirm the last two SSE events are:

```
event: updates
data: {"__review_started__": true}

event: end
data: {}
```

Run:

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload
# In another terminal:
curl -N -X POST http://localhost:8000/threads/{tid}/runs/stream \
  -H "Content-Type: application/json" \
  -d '{"input": {"messages": [{"role": "user", "content": "hi"}]}}' | tail -10
```

- [ ] **Step 3: Commit**

```bash
cd backend && git add choreo/gateway/routers/runs.py
git commit -m "feat(runs): extract invoked_skills and trigger background review in SSE finally block"
```

---

## Task 6: Add review_log API Endpoint + Enforce Builtin/Locked in PATCH

**Files:**
- Modify: `backend/choreo/gateway/routers/skills.py`

- [ ] **Step 1: Add `GET /review_log` endpoint**

Add the following route to `backend/choreo/gateway/routers/skills.py`, before the `import/preview` route:

```python
@router.get("/review_log")
async def get_review_log(limit: int = Query(default=5, ge=1, le=100)):
    store = get_skill_store()
    entries = await store.read_review_log(limit=limit)
    return entries
```

- [ ] **Step 2: Enforce builtin/locked in the PATCH route**

Replace the existing `patch_skill` route:

```python
@router.patch("/{category}/{name}", response_model=Skill)
async def patch_skill(category: str, name: str, body: SkillPatch):
    store = get_skill_store()
    skill = await store.get(f"{category}/{name}")
    if not skill:
        raise HTTPException(404, "skill not found")
    if skill.source == "builtin" and body.content is not None:
        raise HTTPException(403, "内置技能内容不可修改")
    if skill.locked and body.content is not None:
        raise HTTPException(403, "技能已锁定，无法修改内容")
    return await store.update(f"{category}/{name}", body)
```

- [ ] **Step 3: Verify endpoints work**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload
curl http://localhost:8000/api/skills/review_log?limit=3
# Expected: [] (empty JSON array initially)
```

- [ ] **Step 4: Commit**

```bash
cd backend && git add choreo/gateway/routers/skills.py
git commit -m "feat(skills): add GET /review_log endpoint and enforce builtin/locked in PATCH"
```

---

## Task 7: Update Main Agent with New Tools

**Files:**
- Modify: `backend/choreo/agents/choreo_agent.py`

- [ ] **Step 1: Add skill_patch and skill_create to the agent**

Replace the imports line in `backend/choreo/agents/choreo_agent.py`:

```python
from choreo.agents.tools import read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash, skill_view
```

With:

```python
from choreo.agents.tools import read_git_log, send_notification, read_file, write_file, edit_file, list_dir, grep, bash, skill_view
from choreo.agents.tools.skill_tool import skill_patch, skill_create
```

Replace the tools list in `create_agent(...)`:

```python
        tools=[
            read_git_log, send_notification, read_file, write_file,
            edit_file, list_dir, grep, bash, skill_view,
            skill_patch, skill_create,
            mcp_call, mcp_call_auto, mcp_describe,
        ],
```

Replace the system_prompt string to add documentation for the new tools (append after the skill_view line):

```python
            "- skill_patch：更新已有技能（仅在用户明确要求，或任务完成后确认有高复用价值时调用）\n"
            "- skill_create：新建技能（仅在没有现有技能覆盖该场景时调用）\n"
```

Full updated system_prompt:

```python
        system_prompt=(
            "你是 Choreo，一个开发自动化 Agent。帮助用户把重复的开发杂活变成自动运行的脚本。\n"
            "你有以下工具：\n"
            "- read_git_log：读取 git commit 历史\n"
            "- read_file / write_file / edit_file：读写和精确编辑文件\n"
            "- list_dir / grep：目录浏览和内容搜索\n"
            "- bash：执行 bash 命令（需用户确认）\n"
            "- send_notification：发送通知（需用户确认）\n"
            "- skill_view：读取技能库中某个技能（从 Available Skills 列表找 ID）\n"
            "- skill_patch：更新已有技能（仅在用户明确要求，或任务完成后确认有高复用价值时调用）\n"
            "- skill_create：新建技能（仅在没有现有技能覆盖该场景时调用）\n"
            "- mcp_call：调用 MCP server 工具（从 Available MCP Tools 列表找 server/tool）\n"
            "- mcp_describe：查询某个 MCP 工具的完整参数 schema（不确定参数类型时先查）\n"
            "\n"
            "使用 GitHub MCP 工具时：需要当前用户信息（用户名、仓库列表等）时，"
            "先调用 get_me 工具获取认证用户信息，不要猜测用户名。\n"
            "\n"
            "修改文件前先用 read_file；执行 bash 和发送通知前必须等用户确认。"
        ),
```

- [ ] **Step 2: Restart backend and confirm no import errors**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload
# Should start without errors; confirm in logs
```

- [ ] **Step 3: Commit**

```bash
cd backend && git add choreo/agents/choreo_agent.py
git commit -m "feat(agent): add skill_patch and skill_create to main agent tool set"
```

---

## Task 8: Update config.yaml with review_model

**Files:**
- Modify: `backend/config.example.yaml`

- [ ] **Step 1: Add review_model field to config.example.yaml**

After the `active_model:` line, add:

```yaml
review_model: deepseek-chat   # 复盘使用的模型；不填则复用 active_model
```

The relevant section in `config.example.yaml` becomes:

```yaml
active_model: deepseek-chat

review_model: deepseek-chat   # 复盘使用的模型；不填则复用 active_model

active_sandbox: local-dev
```

- [ ] **Step 2: Commit**

```bash
cd backend && git add config.example.yaml
git commit -m "docs(config): add review_model field to config.example.yaml"
```

---

## Task 9: Frontend — Extend Skill Types and Add review_log API

**Files:**
- Modify: `frontend/src/api/skills.ts`

- [ ] **Step 1: Extend Skill interface and add review_log API**

In `frontend/src/api/skills.ts`:

Replace the `Skill` interface with:

```typescript
export interface Skill {
  id: string;
  category: string;
  name: string;
  description: string;
  version: string;
  author: string;
  tags: string[];
  content: string;
  source: "manual" | "auto" | "builtin" | "ai_review";
  state: "active" | "stale" | "archived";
  pinned: boolean;
  locked: boolean;
  use_count: number;
  view_count: number;
  patch_count: number;
  last_activity_at: number | null;
  last_reviewed_at: number | null;
  last_reviewed_by: string | null;
}
```

Replace the `SkillPatch` interface with:

```typescript
export interface SkillPatch {
  description?: string;
  version?: string;
  tags?: string[];
  content?: string;
  pinned?: boolean;
  state?: "active" | "archived";
  locked?: boolean;
}
```

Add the following interfaces and function at the end of the file:

```typescript
export interface ReviewLogEntry {
  thread_id: string;
  ts: number;
  updated: string[];
  created: string[];
}

export const getReviewLog = (limit = 1): Promise<ReviewLogEntry[]> =>
  fetch(`${BASE}/review_log?limit=${limit}`).then((r) => r.json());
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: No errors related to Skill type

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/api/skills.ts
git commit -m "feat(frontend): extend Skill type with locked/last_reviewed fields, add getReviewLog API"
```

---

## Task 10: Frontend — Handle review_started Signal in useChat

**Files:**
- Modify: `frontend/src/hooks/useChat.ts`

- [ ] **Step 1: Add SKILLS_KEY constant and review_started handling**

In `frontend/src/hooks/useChat.ts`:

After the `THREADS_KEY` constant, add:

```typescript
export const SKILLS_KEY = "/api/skills/?";
```

Inside the `sendMessage` function, after the `for await (const chunk of stream)` loop block, add a variable before the loop:

```typescript
    let reviewStarted = false;
```

Inside the `if (chunk.event === "updates")` block, add at the very beginning (before the `data.__interrupt__` check):

```typescript
          // Skill review signal — mark for post-loop handling
          if (data.__review_started__ !== undefined) {
            if (data.__review_started__ === true) {
              reviewStarted = true;
            }
            continue;
          }
```

After the `for await` loop ends (before the `catch`/`finally` block), add:

```typescript
      if (reviewStarted) {
        mutate(SKILLS_KEY);
        setTimeout(() => mutate(SKILLS_KEY), 15_000);
      }
```

Full updated `sendMessage` relevant section after changes:

```typescript
  const sendMessage = useCallback(async (text: string, context?: Record<string, unknown>) => {
    addMessage({ role: "user", content: text });
    setStreaming(true);

    try {
      const tid = await ensureThread();
      const stream = client.runs.stream(tid, "choreo", {
        input: { messages: [{ role: "user", content: text }] },
        streamMode: ["messages", "updates", "custom", "tasks", "values"],
        ...(context && Object.keys(context).length > 0 ? { context } : {}),
      } as any);

      let reviewStarted = false;

      for await (const chunk of stream as any) {
        // ── LLM token 流 ─────────────────────────────────────────
        if (chunk.event === "messages") {
          const msgs: any[] = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs) {
            if (!msg) continue;

            const reasoning = msg.additional_kwargs?.reasoning_content;
            if (reasoning) appendThinking(reasoning);

            const content = msg.content;
            if (typeof content === "string") {
              if (content) appendToken(content);
            } else if (Array.isArray(content)) {
              for (const block of content) {
                if (block.type === "thinking" || block.type === "reasoning") {
                  const t = block.thinking ?? block.reasoning ?? "";
                  if (t) appendThinking(t);
                } else if (block.type === "text" && block.text) {
                  appendToken(block.text);
                }
              }
            }
          }
        }

        // ── 节点状态更新 ─────────────────────────────────────────
        if (chunk.event === "updates") {
          const data = chunk.data ?? {};

          // Skill review signal
          if (data.__review_started__ !== undefined) {
            if (data.__review_started__ === true) reviewStarted = true;
            continue;
          }

          // HITL 中断
          if (data.__interrupt__) {
            const interruptValue = data.__interrupt__[0]?.value;
            if (interruptValue?.action_requests) {
              openReview({ threadId: tid, ...interruptValue });
            }
            break;
          }

          // model 节点：agent 决定调用工具
          const modelMsgs: any[] = data?.model?.messages ?? [];
          for (const msg of modelMsgs) {
            const toolCalls = msg?.tool_calls;
            if (Array.isArray(toolCalls) && toolCalls.length > 0) {
              finalizeToken();
              addMessage({
                role: "assistant",
                content: typeof msg.content === "string" ? msg.content : "",
                tool_calls: toolCalls.map((tc: any) => ({
                  id: tc.id ?? "",
                  name: tc.name ?? tc.function?.name ?? "",
                  args: tc.args ?? tc.function?.arguments ?? {},
                })),
              });
            }
          }

          // tools 节点：工具执行结果
          const toolsMsgs: any[] = data?.tools?.messages ?? [];
          for (const msg of toolsMsgs) {
            if (msg?.type === "tool" || msg?.role === "tool") {
              addMessage({
                role: "tool",
                content: typeof msg.content === "string" ? msg.content : JSON.stringify(msg.content),
                tool_name: msg.name ?? "",
                tool_call_id: msg.tool_call_id ?? "",
              });
            }
          }
        }

        // ── tasks 事件 ──────────────────────────────────────────
        if (chunk.event === "tasks") {
          const task = chunk.data;
          if (task?.interrupts?.length > 0) {
            const interruptValue = task.interrupts[0]?.value;
            if (interruptValue?.action_requests) {
              openReview({ threadId: tid, ...interruptValue });
              break;
            }
          }
        }

        // ── 自定义进度事件 ────────────────────────────────────────
        if (chunk.event === "custom") {
          const status = chunk.data?.status ?? chunk.data?.message;
          if (status) {
            addMessage({ role: "system", content: `⚙️ ${status}` });
          }
        }
      }

      if (reviewStarted) {
        mutate(SKILLS_KEY);
        setTimeout(() => mutate(SKILLS_KEY), 15_000);
      }
    } finally {
      finalizeToken();
      setStreaming(false);
      mutate(THREADS_KEY);
    }
  }, []);
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/hooks/useChat.ts
git commit -m "feat(frontend): handle __review_started__ signal with delayed SKILLS_KEY mutate"
```

---

## Task 11: Frontend — Lock Toggle, AI Badge, Review Summary

**Files:**
- Modify: `frontend/src/components/Skills/SkillCard.tsx`
- Modify: `frontend/src/pages/CustomizeSkillsPage.tsx`

- [ ] **Step 1: Read SkillCard.tsx to understand its current interface**

```bash
cat frontend/src/components/Skills/SkillCard.tsx
```

- [ ] **Step 2: Add lock toggle to CustomizeSkillsPage header**

In `frontend/src/pages/CustomizeSkillsPage.tsx`, in the right panel header where the active toggle and menu button are, add a lock toggle button between the active switch and the menu button.

Find the `<div className="flex items-center gap-3 flex-shrink-0">` in the header and add the lock button:

```tsx
              {/* Lock toggle */}
              <button
                onClick={() => {
                  if (selectedSkill.source !== "builtin") {
                    patch({ locked: !selectedSkill.locked });
                  }
                }}
                disabled={busy || selectedSkill.source === "builtin"}
                title={
                  selectedSkill.source === "builtin"
                    ? "内置技能不可解锁"
                    : selectedSkill.locked
                    ? "已锁定（AI 不可修改）— 点击解锁"
                    : "未锁定 — 点击锁定"
                }
                className={`p-1.5 rounded-lg transition-colors disabled:opacity-40
                  ${selectedSkill.locked || selectedSkill.source === "builtin"
                    ? "text-amber-500 hover:bg-amber-50 dark:hover:bg-amber-950/20"
                    : "text-[#bbb] hover:text-[#666] hover:bg-[#e8e4dc] dark:hover:bg-[#1e1e1e]"
                  }`}
              >
                {selectedSkill.locked || selectedSkill.source === "builtin" ? (
                  /* Locked icon */
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <rect x="3" y="7" width="10" height="7" rx="1.5" />
                    <path d="M5 7V5a3 3 0 016 0v2" />
                  </svg>
                ) : (
                  /* Unlocked icon */
                  <svg className="w-4 h-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <rect x="3" y="7" width="10" height="7" rx="1.5" />
                    <path d="M5 7V5a3 3 0 016 0" />
                  </svg>
                )}
              </button>
```

- [ ] **Step 3: Add AI badge to SkillCard**

Read `frontend/src/components/Skills/SkillCard.tsx` and add a small AI badge to the card when `skill.last_reviewed_at` is within the last 24 hours.

Find where the skill name is rendered in SkillCard and add after or above it:

```tsx
{/* AI badge */}
{skill.last_reviewed_at && Date.now() / 1000 - skill.last_reviewed_at < 86400 && (
  <span
    title={`AI 于 ${Math.round((Date.now() / 1000 - skill.last_reviewed_at) / 60)} 分钟前更新`}
    className="ml-1 inline-flex items-center px-1 py-0.5 rounded text-[9px] font-semibold bg-blue-100 dark:bg-blue-950/40 text-blue-500 dark:text-blue-400 leading-none"
  >
    ✦ AI
  </span>
)}
```

The exact placement depends on SkillCard's current structure (read first in Step 1). The badge should appear next to the skill name.

- [ ] **Step 4: Add review summary bar in the skills panel header**

In `frontend/src/pages/CustomizeSkillsPage.tsx`, add a review summary below the search bar in the left panel. Add imports at the top of the file:

```tsx
import { useEffect, useState } from "react";
import { getReviewLog, type ReviewLogEntry } from "@/api/skills";
```

Add state for the review log:

```tsx
  const [lastReview, setLastReview] = useState<ReviewLogEntry | null>(null);
```

Add a `useEffect` to load the last review entry (add after the existing `useEffect` for file content):

```tsx
  useEffect(() => {
    getReviewLog(1).then((entries) => {
      const entry = entries[0] ?? null;
      // Only show if it has actual updates
      if (entry && (entry.updated.length > 0 || entry.created.length > 0)) {
        setLastReview(entry);
      } else {
        setLastReview(null);
      }
    }).catch(() => {});
  }, [allSkills]);  // re-fetch whenever skills refresh
```

Add the summary bar in the left panel, between the search bar and the skill list (after the search div and before the `<div className="flex-1 overflow-y-auto">`):

```tsx
        {/* Review summary */}
        {lastReview && (
          <div className="mx-4 mb-2 px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-950/20 border border-blue-100 dark:border-blue-900/30">
            <p className="text-[10.5px] text-blue-600 dark:text-blue-400">
              上次对话
              {lastReview.updated.length > 0 && ` 更新了 ${lastReview.updated.length} 个技能`}
              {lastReview.created.length > 0 && ` · 新建了 ${lastReview.created.length} 个技能`}
            </p>
          </div>
        )}
```

- [ ] **Step 5: Verify UI in browser**

```bash
cd frontend && pnpm dev
```

Open `http://localhost:5173` → Navigate to Skills page. Verify:
- Lock icon appears in detail panel header and toggles correctly
- Review summary bar appears after a conversation with background review
- AI badge appears on skills with `last_reviewed_at` within 24h

- [ ] **Step 6: Commit**

```bash
cd frontend && git add src/pages/CustomizeSkillsPage.tsx src/components/Skills/SkillCard.tsx
git commit -m "feat(frontend): add lock toggle, AI badge, and review summary to skills panel"
```

---

## Task 12: Run Full Test Suite

- [ ] **Step 1: Run all backend tests**

```bash
cd backend && uv run pytest tests/ -v --tb=short
```

Expected: All tests pass

- [ ] **Step 2: Check TypeScript types**

```bash
cd frontend && pnpm tsc --noEmit
```

Expected: No errors

- [ ] **Step 3: Smoke-test the full flow**

1. Start backend: `cd backend && uv run uvicorn choreo.gateway.app:app --reload`
2. Start frontend: `cd frontend && pnpm dev`
3. Send a message to the agent about a coding task
4. Watch the SSE stream end with `__review_started__: true`
5. Wait 15 seconds, observe the Skills panel refresh
6. Verify the review summary bar appears if skills were updated
7. Test lock toggle: lock a skill, ask agent to update it, confirm rejection message

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat(skills): complete skill self-evolution — write tools, background review, frontend integration"
```
