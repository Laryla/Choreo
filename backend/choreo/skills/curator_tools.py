# backend/choreo/skills/curator_tools.py
"""Tools exclusively used by the SkillCurator LLM agent."""

from langchain_core.tools import tool
from choreo.skills import get_skill_store
from choreo.models.skill import SkillPatch


@tool
async def skill_view(skill_id: str) -> str:
    """Read the full content of a skill (curator use only).

    Args:
        skill_id: Skill ID in 'category/name' format.
    """
    store = get_skill_store()
    skill = await store.get(skill_id)
    if skill is None:
        return f"Skill '{skill_id}' not found."
    return f"# {skill.name}\n\ndescription: {skill.description}\nsource: {skill.source}\nuse_count: {skill.use_count}\n\n{skill.content}"


@tool
async def skill_patch(
    skill_id: str,
    content: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """Update a skill's content or metadata during consolidation (curator use only).

    Args:
        skill_id: Skill ID in 'category/name' format.
        content: New Markdown body.
        description: New one-line description.
        tags: New tags list (≤ 3 items).
    """
    store = get_skill_store()
    skill = await store.get(skill_id)
    if skill is None:
        return f"Skill '{skill_id}' not found."
    if skill.locked:
        return f"Skill '{skill_id}' is locked and cannot be modified."
    if skill.source == "builtin":
        return f"Skill '{skill_id}' is a built-in and cannot be modified."

    patch = SkillPatch(content=content, description=description, tags=tags)
    await store.update(skill_id, patch)
    return f"Updated '{skill_id}' successfully."


@tool
async def skill_archive(skill_id: str, reason: str = "") -> str:
    """Archive a skill (mark state=archived). Use after merging its content into another skill.

    Args:
        skill_id: Skill ID to archive.
        reason: Brief reason (for logging).
    """
    store = get_skill_store()
    skill = await store.get(skill_id)
    if skill is None:
        return f"Skill '{skill_id}' not found."
    if skill.locked:
        return f"Skill '{skill_id}' is locked and cannot be archived."
    if skill.source == "builtin":
        return f"Skill '{skill_id}' is a built-in and cannot be archived."
    if skill.pinned:
        return f"Skill '{skill_id}' is pinned. Unpin it first before archiving."

    await store.update(skill_id, SkillPatch(state="archived"))
    return f"Archived '{skill_id}'. Reason: {reason or 'consolidated'}"
