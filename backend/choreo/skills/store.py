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
    "locked": False,
    "source": "manual",
    "last_reviewed_at": None,
    "last_reviewed_by": None,
}


def _parse_skill_md(text: str) -> tuple[dict, str]:
    """Split SKILL.md into (frontmatter_dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = yaml.safe_load(text[3:end]) or {}
    # text[end:] starts with "\n---", skip past the closing delimiter line
    after = text[end + 1:]  # skip leading \n → starts with "---..."
    body = after.lstrip("-").lstrip("\n").strip()
    return fm, body


def _write_skill_md(fm: dict, body: str) -> str:
    fm_text = yaml.dump(fm, allow_unicode=True, default_flow_style=False).rstrip()
    return f"---\n{fm_text}\n---\n\n{body}"


class LocalSkillStore:
    def __init__(self, skills_dir: str | Path) -> None:
        self._root = Path(skills_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._usage_lock = asyncio.Lock()

    # ── directory helpers ──────────────────────────────────────────────

    def _active_dir(self, skill_id: str) -> Path:
        cat, name = skill_id.split("/", 1)
        return self._root / cat / name

    def _archived_dir(self, skill_id: str) -> Path:
        cat, name = skill_id.split("/", 1)
        return self._root / ".archived" / cat / name

    def _skill_dir(self, skill_id: str) -> Path | None:
        """Return the actual directory (active or archived), or None."""
        d = self._active_dir(skill_id)
        if d.exists():
            return d
        d = self._archived_dir(skill_id)
        if d.exists():
            return d
        return None

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
            related_skills=fm.get("related_skills") or [],
            content=body,
            source=u["source"],
            state=u["state"],
            pinned=bool(u["pinned"]),
            locked=bool(u["locked"]),
            use_count=int(u["use_count"]),
            view_count=int(u["view_count"]),
            patch_count=int(u["patch_count"]),
            last_activity_at=u["last_activity_at"],
            last_reviewed_at=u["last_reviewed_at"],
            last_reviewed_by=u["last_reviewed_by"],
            arguments=fm.get("arguments", None),
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

        # Active skills: _root/category/name/SKILL.md
        if state != "archived":
            for skill_md in self._root.glob("*/*/SKILL.md"):
                skill_id = f"{skill_md.parent.parent.name}/{skill_md.parent.name}"
                entry = usage.get(skill_id, {})
                if state == "active" and entry.get("state", "active") != "active":
                    continue
                skill = await asyncio.to_thread(self._parse_dir, skill_md.parent, entry)
                if skill:
                    skills.append(skill)

        # Archived skills: _root/.archived/category/name/SKILL.md
        if state != "active":
            archived_root = self._root / ".archived"
            if archived_root.exists():
                for skill_md in archived_root.glob("*/*/SKILL.md"):
                    skill_id = f"{skill_md.parent.parent.name}/{skill_md.parent.name}"
                    entry = {**usage.get(skill_id, {}), "state": "archived"}
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
                line = f"  {pin}{s.id}: {s.description[:120]}"
                if s.related_skills:
                    line += f"  → see also: {', '.join(s.related_skills)}"
                lines.append(line)
        return "\n".join(lines)

    async def get(self, skill_id: str) -> Skill | None:
        if len(skill_id.split("/", 1)) != 2:
            return None
        skill_dir = self._skill_dir(skill_id)
        if skill_dir is None:
            return None
        usage = await self._read_usage()
        entry = usage.get(skill_id, {})
        # Infer state from physical location if not in usage
        if skill_dir == self._archived_dir(skill_id):
            entry = {**entry, "state": "archived"}
        return await asyncio.to_thread(self._parse_dir, skill_dir, entry)

    async def list_files(self, skill_id: str) -> list[str]:
        if len(skill_id.split("/", 1)) != 2:
            return []
        skill_dir = self._skill_dir(skill_id)
        if skill_dir is None:
            return []
        items: list[str] = []
        for f in skill_dir.iterdir():
            if f.name.startswith("."):
                continue
            if f.is_dir():
                items.append(f.name + "/")
            elif f.is_file() and f.name not in _EXCLUDED_FILES:
                items.append(f.name)
        # directories first, then files, both alphabetical
        return sorted(items, key=lambda x: (not x.endswith("/"), x.lower()))

    async def read_file(self, skill_id: str, file_path: str) -> str:
        if len(skill_id.split("/", 1)) != 2:
            raise FileNotFoundError("Invalid skill id")
        raw_dir = self._skill_dir(skill_id)
        if raw_dir is None:
            raise FileNotFoundError(f"Skill not found: {skill_id}")
        skill_dir = raw_dir.resolve()
        target = (skill_dir / file_path).resolve()
        if not str(target).startswith(str(skill_dir)):
            raise PermissionError("Path traversal detected")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        return await asyncio.to_thread(target.read_text, "utf-8", "replace")

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
        if data.related_skills:
            fm["related_skills"] = data.related_skills
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
        skill_dir = self._skill_dir(skill_id)
        assert skill_dir is not None

        # Physical move on state change
        if patch.state == "archived" and skill_dir == self._active_dir(skill_id):
            dest = self._archived_dir(skill_id)
            await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.move, str(skill_dir), str(dest))
            skill_dir = dest
        elif patch.state == "active" and skill_dir == self._archived_dir(skill_id):
            dest = self._active_dir(skill_id)
            await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(shutil.move, str(skill_dir), str(dest))
            skill_dir = dest

        fm: dict[str, Any] = {
            "name": skill.name,
            "description": patch.description if patch.description is not None else skill.description,
            "version": patch.version if patch.version is not None else skill.version,
            "author": skill.author,
            "tags": patch.tags if patch.tags is not None else skill.tags,
        }
        if skill.arguments is not None:
            fm["arguments"] = skill.arguments
        effective_related = patch.related_skills if patch.related_skills is not None else skill.related_skills
        if effective_related:
            fm["related_skills"] = effective_related
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
            if patch.locked is not None:
                entry["locked"] = patch.locked
            if patch.last_reviewed_at is not None:
                entry["last_reviewed_at"] = patch.last_reviewed_at
            if patch.last_reviewed_by is not None:
                entry["last_reviewed_by"] = patch.last_reviewed_by
            if patch.content is not None or patch.description is not None:
                entry["patch_count"] = entry.get("patch_count", 0) + 1
            entry["last_activity_at"] = int(time.time())
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

    async def delete(self, skill_id: str) -> None:
        if len(skill_id.split("/", 1)) != 2:
            return
        skill_dir = self._skill_dir(skill_id)
        if skill_dir and skill_dir.exists():
            await asyncio.to_thread(shutil.rmtree, skill_dir)
        async with self._usage_lock:
            usage = await self._read_usage()
            usage.pop(skill_id, None)
            await self._write_usage(usage)
