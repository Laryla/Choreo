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
    related_skills: list[str] | None = None,
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
        description: New one-line description (≤80 chars)
        tags: New tag list (≤ 3 items, replaces existing)
        related_skills: Skill IDs that complement this one (e.g. ['git/commit-message'])

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
        related_skills=related_skills,
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
    related_skills: list[str] | None = None,
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
        description: ≤80 chars answering "When to use" —
            e.g. "Run Python projects with uv (install, add, run)."
        content: Markdown body. Before writing, call skill_view on a similar
            existing builtin skill and follow its structure as a template.
            Don't invent a format from scratch. Keep under 15 KB.
            No narrative prose — actionable content only.
        tags: Optional list of ≤ 3 tags
        related_skills: Skill IDs that complement this one,
            e.g. ['python/uv-project', 'debug/error-diagnosis']

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

    await store.create(SkillCreate(
        category=category,
        name=name,
        description=description,
        content=content,
        tags=tags or [],
        source="ai_review",
        related_skills=related_skills or [],
    ))

    await store.update(skill_id, SkillPatch(
        last_reviewed_at=now,
        last_reviewed_by=thread_id,
    ))

    siblings = await store.list_by_category(category)
    sibling_lines = "\n".join(
        f"  - {s.id}: {s.description[:80]}"
        for s in siblings if s.id != skill_id
    )
    sibling_block = f"\n同 category 现有技能（请确认无语义重复）：\n{sibling_lines}" if sibling_lines else ""

    return f"技能 '{skill_id}' 创建成功。{sibling_block}"
