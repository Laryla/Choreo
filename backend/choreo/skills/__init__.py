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
