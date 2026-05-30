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

    with zf:
        md_entries = [
            n for n in zf.namelist()
            if n.endswith(".md") and not n.startswith("__MACOSX")
        ]
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
