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
