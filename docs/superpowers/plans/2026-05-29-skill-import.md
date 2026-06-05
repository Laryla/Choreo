# Skill Import Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "新建技能" form flow with a file-upload import flow supporting single `.md` and `.zip` packages.

**Architecture:** Backend adds `importer.py` (parse logic + in-memory session store) and two new routes on the existing skills router. Frontend adds a `SkillImportModal` component with a 3-step state machine (`category → select → conflict → done`) and wires it into `CustomizeSkillsPage`.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript/Tailwind (frontend), `zipfile` stdlib (zip parsing), `pytest-asyncio` (tests)

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `backend/choreo/skills/importer.py` | parse `.md`/`.zip`, session store |
| Modify | `backend/choreo/gateway/routers/skills.py` | add `/import/preview` and `/import/confirm` routes |
| Create | `backend/tests/test_importer.py` | unit tests for importer |
| Modify | `frontend/src/api/skills.ts` | add `previewImport`, `confirmImport` |
| Create | `frontend/src/components/Skills/SkillImportModal.tsx` | 3-step import modal |
| Modify | `frontend/src/pages/CustomizeSkillsPage.tsx` | replace "新建技能" with import button |

---

### Task 1: parse_md — parse a single `.md` file into SkillCreate

**Files:**
- Create: `backend/choreo/skills/importer.py`
- Create: `backend/tests/test_importer.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_importer.py
import pytest
from choreo.skills.importer import parse_md
from choreo.models.skill import SkillCreate


def test_parse_md_full_frontmatter():
    text = """\
---
name: frontend-design
description: Use when designing frontend components
version: 1.2.0
author: alice
tags:
  - design
  - ui
---

# Frontend Design Skill

Body content here.
"""
    result = parse_md(text, category="design")
    assert isinstance(result, SkillCreate)
    assert result.name == "frontend-design"
    assert result.category == "design"
    assert result.description == "Use when designing frontend components"
    assert result.version == "1.2.0"
    assert result.author == "alice"
    assert result.tags == ["design", "ui"]
    assert "Body content here" in result.content


def test_parse_md_minimal_frontmatter():
    text = """\
---
name: my-skill
description: Use when doing something useful
---

Some body.
"""
    result = parse_md(text, category="imported")
    assert result.name == "my-skill"
    assert result.version == "1.0.0"
    assert result.author == "user"
    assert result.tags == []


def test_parse_md_no_frontmatter_raises():
    text = "Just plain text with no frontmatter."
    with pytest.raises(ValueError, match="missing frontmatter"):
        parse_md(text, category="imported")


def test_parse_md_missing_name_raises():
    text = """\
---
description: Use when something
---
body
"""
    with pytest.raises(ValueError, match="missing 'name'"):
        parse_md(text, category="imported")


def test_parse_md_missing_description_raises():
    text = """\
---
name: my-skill
---
body
"""
    with pytest.raises(ValueError, match="missing 'description'"):
        parse_md(text, category="imported")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_importer.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'choreo.skills.importer'`

- [ ] **Step 3: Implement parse_md**

```python
# backend/choreo/skills/importer.py
import io
import time
import uuid
import zipfile
from pathlib import PurePosixPath

import yaml

from choreo.models.skill import SkillCreate


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    after = text[end + 1:].lstrip("-").lstrip("\n").strip()
    return fm, after


def parse_md(text: str, category: str) -> SkillCreate:
    fm, body = _split_frontmatter(text)
    if not fm:
        raise ValueError("missing frontmatter")
    if not fm.get("name"):
        raise ValueError("missing 'name' in frontmatter")
    if not fm.get("description"):
        raise ValueError("missing 'description' in frontmatter")
    return SkillCreate(
        category=category,
        name=str(fm["name"]),
        description=str(fm["description"]),
        version=str(fm.get("version", "1.0.0")),
        author=str(fm.get("author", "user")),
        tags=list(fm.get("tags") or []),
        content=body,
        source="manual",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_importer.py::test_parse_md_full_frontmatter tests/test_importer.py::test_parse_md_minimal_frontmatter tests/test_importer.py::test_parse_md_no_frontmatter_raises tests/test_importer.py::test_parse_md_missing_name_raises tests/test_importer.py::test_parse_md_missing_description_raises -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/skills/importer.py backend/tests/test_importer.py
git commit -m "feat(skills): add parse_md for single .md skill import"
```

---

### Task 2: parse_zip — extract multiple skills from a zip archive

**Files:**
- Modify: `backend/choreo/skills/importer.py`
- Modify: `backend/tests/test_importer.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_importer.py`:

```python
import io
import zipfile
from choreo.skills.importer import parse_zip


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_parse_zip_with_directory_structure():
    md = """\
---
name: frontend-design
description: Use when designing UIs
---
body
"""
    data = _make_zip({"design/frontend-design.md": md})
    results = parse_zip(data)
    assert len(results) == 1
    assert results[0].category == "design"
    assert results[0].name == "frontend-design"


def test_parse_zip_top_level_md_uses_imported_category():
    md = """\
---
name: my-skill
description: Use when doing stuff
---
body
"""
    data = _make_zip({"my-skill.md": md})
    results = parse_zip(data)
    assert len(results) == 1
    assert results[0].category == "imported"


def test_parse_zip_multiple_skills():
    md1 = "---\nname: skill-a\ndescription: Use when A\n---\nbody"
    md2 = "---\nname: skill-b\ndescription: Use when B\n---\nbody"
    data = _make_zip({"cat1/skill-a.md": md1, "cat2/skill-b.md": md2})
    results = parse_zip(data)
    assert len(results) == 2
    names = {r.name for r in results}
    assert names == {"skill-a", "skill-b"}


def test_parse_zip_skips_malformed_md():
    good = "---\nname: good\ndescription: Use when good\n---\nbody"
    bad = "no frontmatter at all"
    data = _make_zip({"cat/good.md": good, "cat/bad.md": bad})
    results, skipped = parse_zip(data)
    assert len(results) == 1
    assert "cat/bad.md" in skipped


def test_parse_zip_empty_raises():
    data = _make_zip({"readme.txt": "hello"})
    with pytest.raises(ValueError, match="no .md files"):
        parse_zip(data)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_importer.py -k "zip" -v 2>&1 | head -20
```

Expected: ImportError or AttributeError (parse_zip not yet defined)

- [ ] **Step 3: Implement parse_zip**

Note: `test_parse_zip_skips_malformed_md` expects `parse_zip` to return a tuple `(results, skipped)`. Update `parse_zip` accordingly (and fix `test_parse_zip_with_directory_structure` etc. to unpack the tuple):

```python
# Add to backend/choreo/skills/importer.py

def parse_zip(data: bytes) -> tuple[list[SkillCreate], list[str]]:
    """Parse all .md files from a zip archive.

    Returns (skills, skipped_paths) where skipped_paths are files
    that failed to parse.
    """
    buf = io.BytesIO(data)
    try:
        zf = zipfile.ZipFile(buf)
    except zipfile.BadZipFile as exc:
        raise ValueError("not a valid zip file") from exc

    md_entries = [n for n in zf.namelist() if n.endswith(".md") and not n.startswith("__MACOSX")]
    if not md_entries:
        raise ValueError("no .md files found in zip")

    skills: list[SkillCreate] = []
    skipped: list[str] = []

    for entry in md_entries:
        text = zf.read(entry).decode("utf-8", errors="replace")
        parts = PurePosixPath(entry).parts
        # derive category from directory; top-level → "imported"
        category = parts[-2] if len(parts) >= 2 else "imported"
        try:
            skill = parse_md(text, category=category)
            skills.append(skill)
        except ValueError:
            skipped.append(entry)

    return skills, skipped
```

Also update the non-skipped tests to unpack the tuple:

```python
def test_parse_zip_with_directory_structure():
    ...
    results, skipped = parse_zip(data)
    assert skipped == []
    assert len(results) == 1
    ...

def test_parse_zip_top_level_md_uses_imported_category():
    ...
    results, skipped = parse_zip(data)
    assert results[0].category == "imported"

def test_parse_zip_multiple_skills():
    ...
    results, skipped = parse_zip(data)
    assert len(results) == 2
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_importer.py -v
```

Expected: all tests PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/skills/importer.py backend/tests/test_importer.py
git commit -m "feat(skills): add parse_zip for bulk skill import from zip"
```

---

### Task 3: Session store — hold parsed skills between preview and confirm

**Files:**
- Modify: `backend/choreo/skills/importer.py`
- Modify: `backend/tests/test_importer.py`

- [ ] **Step 1: Write failing tests**

Add to `backend/tests/test_importer.py`:

```python
import asyncio
from choreo.skills.importer import create_session, get_session, SESSION_TTL_SECONDS


def test_create_and_get_session():
    skills = [SkillCreate(category="cat", name="s1", description="Use when x")]
    sid = create_session(skills)
    assert isinstance(sid, str) and len(sid) == 36  # UUID
    result = get_session(sid)
    assert result is not None
    assert len(result) == 1
    assert result[0].name == "s1"


def test_get_session_unknown_returns_none():
    result = get_session("nonexistent-id")
    assert result is None


def test_session_expires():
    skills = [SkillCreate(category="cat", name="s2", description="Use when y")]
    sid = create_session(skills, ttl=0)  # expires immediately
    import time; time.sleep(0.01)
    assert get_session(sid) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_importer.py -k "session" -v 2>&1 | head -20
```

Expected: ImportError (create_session not defined)

- [ ] **Step 3: Implement session store**

Add to `backend/choreo/skills/importer.py` (after existing imports):

```python
SESSION_TTL_SECONDS = 600  # 10 minutes

_sessions: dict[str, tuple[list[SkillCreate], float]] = {}


def create_session(skills: list[SkillCreate], ttl: int = SESSION_TTL_SECONDS) -> str:
    sid = str(uuid.uuid4())
    _sessions[sid] = (skills, time.time() + ttl)
    return sid


def get_session(session_id: str) -> list[SkillCreate] | None:
    entry = _sessions.get(session_id)
    if entry is None:
        return None
    skills, expires_at = entry
    if time.time() > expires_at:
        del _sessions[session_id]
        return None
    return skills
```

- [ ] **Step 4: Run all importer tests**

```bash
cd backend && uv run pytest tests/test_importer.py -v
```

Expected: all tests PASSED

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/skills/importer.py backend/tests/test_importer.py
git commit -m "feat(skills): add in-memory session store for import preview"
```

---

### Task 4: Backend routes — /import/preview and /import/confirm

**Files:**
- Modify: `backend/choreo/gateway/routers/skills.py`

- [ ] **Step 1: Add imports and Pydantic models at top of skills.py**

Open `backend/choreo/gateway/routers/skills.py`. Add to imports:

```python
import uuid
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from choreo.skills.importer import (
    SESSION_TTL_SECONDS,
    create_session,
    get_session,
    parse_md,
    parse_zip,
)
```

Replace the existing `from fastapi import APIRouter, HTTPException, Query` line.

Add these Pydantic models after the `router = APIRouter()` line:

```python
class PreviewSkill(BaseModel):
    category: str
    name: str
    description: str
    conflict: bool


class ImportPreviewResponse(BaseModel):
    session_id: str
    skills: list[PreviewSkill]


class ImportConfirmBody(BaseModel):
    session_id: str
    selections: list[str]                             # ["category/name", ...]
    conflict_decisions: dict[str, str]                # {"category/name": "overwrite"|"skip"}


class ImportConfirmResponse(BaseModel):
    imported: list[str]
```

- [ ] **Step 2: Add /import/preview route**

Add after the existing `delete_skill` route:

```python
@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(
    file: UploadFile = File(...),
    category: str = Form(default="imported"),
):
    store = get_skill_store()
    data = await file.read()

    filename = file.filename or ""
    if filename.endswith(".zip"):
        try:
            skills, skipped = parse_zip(data)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
    elif filename.endswith(".md"):
        text = data.decode("utf-8", errors="replace")
        try:
            skill = parse_md(text, category=category)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        skills = [skill]
        skipped = []
    else:
        raise HTTPException(400, "仅支持 .md 或 .zip 文件")

    preview_skills: list[PreviewSkill] = []
    for s in skills:
        conflict = await store.get(f"{s.category}/{s.name}") is not None
        preview_skills.append(PreviewSkill(
            category=s.category,
            name=s.name,
            description=s.description,
            conflict=conflict,
        ))

    session_id = create_session(skills)
    return ImportPreviewResponse(session_id=session_id, skills=preview_skills)
```

- [ ] **Step 3: Add /import/confirm route**

```python
@router.post("/import/confirm", response_model=ImportConfirmResponse)
async def import_confirm(body: ImportConfirmBody):
    store = get_skill_store()
    skills = get_session(body.session_id)
    if skills is None:
        raise HTTPException(404, "导入会话已过期，请重新上传文件")

    skill_map = {f"{s.category}/{s.name}": s for s in skills}
    imported: list[str] = []

    for skill_id in body.selections:
        skill = skill_map.get(skill_id)
        if skill is None:
            continue
        decision = body.conflict_decisions.get(skill_id, "overwrite")
        existing = await store.get(skill_id)

        if existing is not None:
            if decision == "skip":
                continue
            from choreo.models.skill import SkillPatch
            await store.update(skill_id, SkillPatch(
                description=skill.description,
                version=skill.version,
                tags=skill.tags,
                content=skill.content,
            ))
        else:
            await store.create(skill)

        imported.append(skill_id)

    return ImportConfirmResponse(imported=imported)
```

- [ ] **Step 4: Start the backend and smoke-test**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload &
sleep 2

# Test preview with a .md file
echo '---
name: test-skill
description: Use when testing import
---
body content' > /tmp/test-skill.md

curl -s -X POST http://localhost:8000/api/skills/import/preview \
  -F "file=@/tmp/test-skill.md" \
  -F "category=testing" | python3 -m json.tool
```

Expected: JSON with `session_id` and `skills` array containing `test-skill` with `conflict: false`.

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/gateway/routers/skills.py
git commit -m "feat(skills): add /import/preview and /import/confirm routes"
```

---

### Task 5: Frontend API — previewImport and confirmImport

**Files:**
- Modify: `frontend/src/api/skills.ts`

- [ ] **Step 1: Add types and functions**

Open `frontend/src/api/skills.ts`. Append to the end of the file:

```typescript
export interface PreviewSkill {
  category: string;
  name: string;
  description: string;
  conflict: boolean;
}

export interface ImportPreviewResponse {
  session_id: string;
  skills: PreviewSkill[];
}

export interface ImportConfirmBody {
  session_id: string;
  selections: string[];
  conflict_decisions: Record<string, "overwrite" | "skip">;
}

export interface ImportConfirmResponse {
  imported: string[];
}

export const previewImport = (
  file: File,
  category?: string
): Promise<ImportPreviewResponse> => {
  const form = new FormData();
  form.append("file", file);
  if (category) form.append("category", category);
  return fetch(`${BASE}/import/preview`, { method: "POST", body: form }).then(
    (r) => {
      if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.detail ?? `${r.status}`)));
      return r.json();
    }
  );
};

export const confirmImport = (
  body: ImportConfirmBody
): Promise<ImportConfirmResponse> =>
  fetch(`${BASE}/import/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.detail ?? `${r.status}`)));
    return r.json();
  });
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -20
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/skills.ts
git commit -m "feat(skills): add previewImport and confirmImport API functions"
```

---

### Task 6: SkillImportModal component

**Files:**
- Create: `frontend/src/components/Skills/SkillImportModal.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/Skills/SkillImportModal.tsx
import { useRef, useState } from "react";
import {
  previewImport,
  confirmImport,
  type PreviewSkill,
} from "@/api/skills";

type Step = "category" | "select" | "conflict" | "done";

interface Props {
  file: File;
  onClose: () => void;
  onDone: () => void;
}

export default function SkillImportModal({ file, onClose, onDone }: Props) {
  const isZip = file.name.endsWith(".zip");

  const [step, setStep] = useState<Step>(isZip ? "select" : "category");
  const [category, setCategory] = useState("imported");
  const [sessionId, setSessionId] = useState("");
  const [skills, setSkills] = useState<PreviewSkill[]>([]);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [decisions, setDecisions] = useState<Record<string, "overwrite" | "skip">>({});
  const [importedCount, setImportedCount] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const skillId = (s: PreviewSkill) => `${s.category}/${s.name}`;

  const runPreview = async (cat?: string) => {
    setLoading(true);
    setError("");
    try {
      const res = await previewImport(file, cat ?? category);
      setSessionId(res.session_id);
      setSkills(res.skills);
      const allIds = new Set(res.skills.map(skillId));
      setChecked(allIds);
      if (isZip) {
        setStep("select");
      } else {
        const conflict = res.skills.some((s) => s.conflict);
        conflict ? setStep("conflict") : await runConfirm(res.session_id, res.skills, {});
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const runConfirm = async (
    sid: string,
    allSkills: PreviewSkill[],
    dec: Record<string, "overwrite" | "skip">
  ) => {
    setLoading(true);
    setError("");
    try {
      const selections = [...checked].filter((id) =>
        allSkills.some((s) => skillId(s) === id)
      );
      const res = await confirmImport({ session_id: sid, selections, conflict_decisions: dec });
      setImportedCount(res.imported.length);
      setStep("done");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const toggleCheck = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const setAllDecisions = (val: "overwrite" | "skip") => {
    const dec: Record<string, "overwrite" | "skip"> = {};
    skills.filter((s) => s.conflict && checked.has(skillId(s))).forEach((s) => {
      dec[skillId(s)] = val;
    });
    setDecisions(dec);
  };

  const conflictSkills = skills.filter((s) => s.conflict && checked.has(skillId(s)));

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white dark:bg-[#1a1a1a] border border-[#ddd9d0] dark:border-[#252525] rounded-xl shadow-xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="px-5 py-4 border-b border-[#eee] dark:border-[#252525] flex items-center justify-between">
          <h2 className="text-[14px] font-semibold text-[#0f0f0f] dark:text-[#e8e8e8]">导入技能</h2>
          <button onClick={onClose} className="text-[#aaa] hover:text-[#555] text-lg leading-none">×</button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {error && (
            <div className="mb-3 text-[12px] text-red-500 bg-red-50 dark:bg-red-900/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          {/* Step: category (single .md only) */}
          {step === "category" && (
            <div>
              <p className="text-[12px] text-[#555] dark:text-[#888] mb-3">
                文件：<span className="font-mono">{file.name}</span>
              </p>
              <label className="block text-[11px] font-semibold text-[#666] dark:text-[#999] mb-1.5 uppercase tracking-wide">
                分类 (Category)
              </label>
              <input
                className="w-full px-3 py-2 rounded-lg border border-[#ddd] dark:border-[#333] bg-white dark:bg-[#111] text-[13px] text-[#1a1a1a] dark:text-[#ccc] focus:outline-none focus:ring-1 focus:ring-[#1e293b]"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="imported"
              />
              <p className="text-[11px] text-[#aaa] mt-1.5">用于组织技能的目录名，如 design / animation</p>
            </div>
          )}

          {/* Step: select (zip) */}
          {step === "select" && skills.length === 0 && (
            <p className="text-[12px] text-[#888]">正在解析文件…</p>
          )}
          {step === "select" && skills.length > 0 && (
            <div>
              <p className="text-[12px] text-[#555] dark:text-[#888] mb-3">
                共找到 {skills.length} 个技能，勾选要导入的：
              </p>
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {skills.map((s) => (
                  <label key={skillId(s)} className="flex items-center gap-2.5 px-3 py-2 rounded-lg border border-[#eee] dark:border-[#252525] bg-[#fafafa] dark:bg-[#111] cursor-pointer">
                    <input
                      type="checkbox"
                      checked={checked.has(skillId(s))}
                      onChange={() => toggleCheck(skillId(s))}
                      className="accent-[#1e293b]"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] font-semibold text-[#1a1a1a] dark:text-[#ddd] truncate">{s.name}</div>
                      <div className="text-[10px] text-[#aaa] font-mono">{s.category}/</div>
                    </div>
                    {s.conflict && (
                      <span className="text-[9px] bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400 px-1.5 py-0.5 rounded font-medium">已存在</span>
                    )}
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* Step: conflict */}
          {step === "conflict" && (
            <div>
              <p className="text-[12px] text-[#555] dark:text-[#888] mb-2">
                以下技能已存在，请选择处理方式：
              </p>
              <div className="flex gap-2 mb-3">
                <button onClick={() => setAllDecisions("overwrite")} className="flex-1 py-1.5 text-[11px] rounded-lg border border-[#ddd] dark:border-[#333] hover:bg-[#f5f5f5] dark:hover:bg-[#222] text-[#555] dark:text-[#999]">全部覆盖</button>
                <button onClick={() => setAllDecisions("skip")} className="flex-1 py-1.5 text-[11px] rounded-lg border border-[#ddd] dark:border-[#333] hover:bg-[#f5f5f5] dark:hover:bg-[#222] text-[#555] dark:text-[#999]">全部跳过</button>
              </div>
              <div className="space-y-2 max-h-52 overflow-y-auto">
                {conflictSkills.map((s) => {
                  const id = skillId(s);
                  const dec = decisions[id] ?? "overwrite";
                  return (
                    <div key={id} className="flex items-center gap-2 px-3 py-2 rounded-lg border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-900/10">
                      <div className="flex-1 text-[12px] font-medium text-[#555] dark:text-[#999] truncate">{id}</div>
                      <button
                        onClick={() => setDecisions((d) => ({ ...d, [id]: "overwrite" }))}
                        className={`px-2.5 py-1 rounded text-[11px] ${dec === "overwrite" ? "bg-[#1e293b] text-white" : "bg-white dark:bg-[#222] border border-[#ddd] dark:border-[#333] text-[#666]"}`}
                      >覆盖</button>
                      <button
                        onClick={() => setDecisions((d) => ({ ...d, [id]: "skip" }))}
                        className={`px-2.5 py-1 rounded text-[11px] ${dec === "skip" ? "bg-[#1e293b] text-white" : "bg-white dark:bg-[#222] border border-[#ddd] dark:border-[#333] text-[#666]"}`}
                      >跳过</button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Step: done */}
          {step === "done" && (
            <div className="text-center py-4">
              <div className="text-3xl mb-2">✅</div>
              <p className="text-[14px] font-semibold text-[#1a1a1a] dark:text-[#e8e8e8]">导入成功</p>
              <p className="text-[12px] text-[#888] mt-1">已导入 {importedCount} 个技能</p>
            </div>
          )}
        </div>

        {/* Footer */}
        {step !== "done" && (
          <div className="px-5 py-3 border-t border-[#eee] dark:border-[#252525] flex justify-end gap-2">
            <button onClick={onClose} className="px-3 py-1.5 rounded-lg text-[12px] text-[#666] hover:bg-[#f5f5f5] dark:hover:bg-[#222]">取消</button>

            {step === "category" && (
              <button
                disabled={loading || !category.trim()}
                onClick={() => runPreview(category)}
                className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
              >{loading ? "解析中…" : "下一步"}</button>
            )}

            {step === "select" && (
              <>
                {skills.length === 0 && (
                  <button
                    disabled={loading}
                    onClick={() => runPreview()}
                    className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
                  >{loading ? "解析中…" : "解析文件"}</button>
                )}
                {skills.length > 0 && (
                  <button
                    disabled={loading || checked.size === 0}
                    onClick={() => {
                      const hasConflict = skills.some((s) => s.conflict && checked.has(skillId(s)));
                      hasConflict ? setStep("conflict") : runConfirm(sessionId, skills, {});
                    }}
                    className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
                  >{loading ? "导入中…" : "下一步"}</button>
                )}
              </>
            )}

            {step === "conflict" && (
              <button
                disabled={loading}
                onClick={() => runConfirm(sessionId, skills, decisions)}
                className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px] disabled:opacity-50"
              >{loading ? "导入中…" : "确认导入"}</button>
            )}
          </div>
        )}
        {step === "done" && (
          <div className="px-5 py-3 border-t border-[#eee] dark:border-[#252525] flex justify-end">
            <button onClick={() => { onDone(); onClose(); }} className="px-4 py-1.5 rounded-lg bg-[#1e293b] text-white text-[12px]">关闭</button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Skills/SkillImportModal.tsx
git commit -m "feat(skills): add SkillImportModal component"
```

---

### Task 7: Wire up import in CustomizeSkillsPage

**Files:**
- Modify: `frontend/src/pages/CustomizeSkillsPage.tsx`

- [ ] **Step 1: Replace "新建技能" button with import flow**

Open `frontend/src/pages/CustomizeSkillsPage.tsx`.

Replace the imports block at the top with:

```tsx
import { useRef, useState } from "react";
import useSWR from "swr";
import SkillCard from "@/components/Skills/SkillCard";
import SkillImportModal from "@/components/Skills/SkillImportModal";
import type { Skill } from "@/api/skills";
```

Replace the state declarations at the top of the component:

```tsx
const [q, setQ] = useState("");
const [tab, setTab] = useState<Tab>("active");
const [importFile, setImportFile] = useState<File | null>(null);
const fileInputRef = useRef<HTMLInputElement>(null);
```

Remove the `editTarget` state and the `SkillEditor` import/usage entirely.

Replace the toolbar button section (the `ml-auto` button):

```tsx
<>
  <input
    ref={fileInputRef}
    type="file"
    accept=".md,.zip"
    className="hidden"
    onChange={(e) => {
      const f = e.target.files?.[0];
      if (f) setImportFile(f);
      e.target.value = "";
    }}
  />
  <button
    onClick={() => fileInputRef.current?.click()}
    className="ml-auto px-3 py-1.5 rounded-lg bg-[#1e293b] dark:bg-[#2a2a2a] text-white text-[12px] hover:bg-[#2d3f57] transition-colors"
  >
    导入技能
  </button>
</>
```

Replace the `SkillEditor` block at the bottom (just before the closing `</div>`) with:

```tsx
{importFile && (
  <SkillImportModal
    file={importFile}
    onClose={() => setImportFile(null)}
    onDone={refresh}
  />
)}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

Expected: no errors

- [ ] **Step 3: Start frontend and test the happy path**

```bash
cd frontend && pnpm dev
```

1. Open `http://localhost:5173/customize/skills`
2. Click **导入技能**
3. Select a `.md` file (create one with valid frontmatter)
4. Enter a category name, click **下一步**
5. Verify the skill appears in the list

- [ ] **Step 4: Test zip import**

Create a test zip:

```bash
mkdir -p /tmp/skill-test/design
cat > /tmp/skill-test/design/my-skill.md << 'EOF'
---
name: my-skill
description: Use when doing my skill things
version: 1.0.0
author: test
tags:
  - test
---

# My Skill

This is the body.
EOF
cd /tmp/skill-test && zip -r /tmp/test-skills.zip design/
```

Import `/tmp/test-skills.zip` through the UI. Verify:
- Step shows checklist with `my-skill` under `design/`
- After confirm, skill appears in the list

- [ ] **Step 5: Test conflict flow**

Import the same `.md` file a second time. Verify:
- Conflict badge shows "已存在"
- 覆盖/跳过 buttons appear
- Both choices work correctly

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/CustomizeSkillsPage.tsx
git commit -m "feat(skills): wire import modal into CustomizeSkillsPage"
```

---

## Self-Review

**Spec coverage:**
- ✅ `.md` upload with category input step
- ✅ `.zip` upload with skill checklist
- ✅ Conflict detection (preview) + resolution (confirm) with overwrite/skip
- ✅ "全部覆盖 / 全部跳过" shortcuts
- ✅ Backend two-endpoint design (preview + confirm)
- ✅ In-memory session store with TTL
- ✅ Category from zip directory structure; top-level → `imported`
- ✅ Malformed `.md` files skipped with path recorded
- ✅ Error handling: invalid type, empty zip, expired session

**Placeholder scan:** None found.

**Type consistency:**
- `PreviewSkill` defined in Task 4 (backend Pydantic) and Task 5 (frontend TS) — field names match.
- `ImportConfirmBody.selections` is `list[str]` (backend) / `string[]` (frontend) — consistent.
- `parse_zip` returns `tuple[list[SkillCreate], list[str]]` — used consistently in Task 4 route.
- `skillId()` helper produces `"category/name"` — matches `selections` format in confirm body.
