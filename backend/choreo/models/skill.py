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
