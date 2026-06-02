import time
from langchain_core.tools import tool
from langgraph.config import get_config
from choreo.skills import get_skill_store
from choreo.models.skill import SkillCreate, SkillPatch

_MAX_CONTENT_BYTES = 15 * 1024  # 15 KB
_MAX_FILE_BYTES = 200 * 1024    # 200 KB


@tool
async def skill_manager(
    action: str,
    skill_id: str = "",
    category: str = "",
    name: str = "",
    description: str = "",
    content: str = "",
    file_path: str = "",
    tags: list[str] | None = None,
    related_skills: list[str] | None = None,
) -> str:
    """Unified skill management tool.

    action:
      read       — Read SKILL.md of skill_id (also records a use)
      list       — List skills; skill_id="category/" to filter by category, "" for all
      create     — Create new skill (requires: category, name, description, content)
      patch      — Update SKILL.md / metadata (requires: skill_id; optional: content,
                   description, tags, related_skills)
      write_file — Write a bundled file into skill dir (requires: skill_id, file_path,
                   content) — use for scripts/, agents/, references/ etc.
      delete     — Delete skill (requires: skill_id)

    Notes:
    - skill_id format: 'category/name', e.g. 'git/weekly-report'
    - For create: content is the Markdown body of SKILL.md (max 15 KB)
    - For write_file: file_path is relative within the skill dir, e.g. 'scripts/parse.py'
    - Built-in skills (source=builtin) cannot be patched or deleted
    - Locked skills cannot be patched, write_file'd, or deleted
    """
    store = get_skill_store()
    config = get_config()
    thread_id = (config.get("configurable") or {}).get("thread_id")

    # ── read ──────────────────────────────────────────────────────────
    if action == "read":
        skill = await store.get(skill_id)
        if skill is None:
            return f"Skill '{skill_id}' not found."
        await store.record_use(skill_id)
        return f"# {skill.name}\n\n{skill.content}"

    # ── list ──────────────────────────────────────────────────────────
    if action == "list":
        if skill_id.endswith("/"):
            cat = skill_id.rstrip("/")
            skills = await store.list_by_category(cat)
        else:
            skills = await store.list_active()
        if not skills:
            return "没有找到技能。"
        lines = [f"- {s.id}: {s.description[:80]}" for s in skills]
        return "\n".join(lines)

    # ── create ────────────────────────────────────────────────────────
    if action == "create":
        if not category or not name or not description or not content:
            return "create 需要 category、name、description、content 四个参数。"
        sid = f"{category}/{name}"
        if await store.get(sid) is not None:
            return f"技能 '{sid}' 已存在，请改用 action=patch 更新内容。"
        if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
            return "内容超过 15KB 限制，请精简后重试。"
        await store.create(SkillCreate(
            category=category, name=name, description=description,
            content=content, tags=tags or [], source="ai_review",
            related_skills=related_skills or [],
        ))
        now = int(time.time())
        await store.update(sid, SkillPatch(last_reviewed_at=now, last_reviewed_by=thread_id))
        siblings = await store.list_by_category(category)
        sibling_lines = "\n".join(
            f"  - {s.id}: {s.description[:80]}"
            for s in siblings if s.id != sid
        )
        sibling_block = f"\n同 category 现有技能（请确认无语义重复）：\n{sibling_lines}" if sibling_lines else ""
        return f"技能 '{sid}' 创建成功。{sibling_block}"

    # ── patch ─────────────────────────────────────────────────────────
    if action == "patch":
        if not skill_id:
            return "patch 需要 skill_id 参数。"
        skill = await store.get(skill_id)
        if skill is None:
            return f"技能 '{skill_id}' 不存在，请先用 action=create 新建。"
        if skill.source == "builtin":
            return "内置技能不可修改（source=builtin）。若需定制，请新建同名覆盖版本。"
        if skill.locked:
            return "技能已被用户锁定（locked=true），无法修改。"
        if content and len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
            return "内容超过 15KB 限制，请精简后重试。"
        now = int(time.time())
        await store.update(skill_id, SkillPatch(
            content=content or None,
            description=description or None,
            tags=tags,
            related_skills=related_skills,
            last_reviewed_at=now,
            last_reviewed_by=thread_id,
        ))
        updated = await store.get(skill_id)
        return f"技能 '{skill_id}' 更新成功（patch_count={updated.patch_count}）。"

    # ── write_file ────────────────────────────────────────────────────
    if action == "write_file":
        if not skill_id or not file_path or not content:
            return "write_file 需要 skill_id、file_path、content 三个参数。"
        skill = await store.get(skill_id)
        if skill is None:
            return f"技能 '{skill_id}' 不存在，请先用 action=create 新建。"
        if skill.locked:
            return "技能已被用户锁定，无法写入文件。"
        if file_path in ("SKILL.md", "skill.md"):
            return "请用 action=patch 修改 SKILL.md，不要用 write_file 覆盖。"
        if len(content.encode("utf-8")) > _MAX_FILE_BYTES:
            return "单文件超过 200KB 限制，请拆分后分多次写入。"
        try:
            await store.write_file(skill_id, file_path, content)
        except PermissionError:
            return f"路径 '{file_path}' 不安全（路径穿越检测），操作被拒绝。"
        return f"文件 '{file_path}' 已写入技能 '{skill_id}'。"

    # ── delete ────────────────────────────────────────────────────────
    if action == "delete":
        if not skill_id:
            return "delete 需要 skill_id 参数。"
        skill = await store.get(skill_id)
        if skill is None:
            return f"技能 '{skill_id}' 不存在。"
        if skill.source == "builtin":
            return "内置技能不可删除（source=builtin）。"
        if skill.locked:
            return "技能已被用户锁定，无法删除。"
        await store.delete(skill_id)
        return f"技能 '{skill_id}' 已删除。"

    return f"未知 action: '{action}'。支持：read / list / create / patch / write_file / delete"
