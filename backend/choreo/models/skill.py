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
