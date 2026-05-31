# backend/choreo/gateway/routers/skills.py
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from choreo.models.skill import Skill, SkillCreate, SkillPatch
from choreo.skills import get_skill_store
from choreo.skills.importer import create_session, get_session, parse_md, parse_zip

router = APIRouter()


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


@router.get("/", response_model=list[Skill])
async def list_skills(
    q: str | None = Query(default=None),
    state: str | None = Query(default=None),
):
    store = get_skill_store()
    if q:
        return await store.search(q)
    return await store.list_all(state=state)


@router.post("/", response_model=Skill, status_code=201)
async def create_skill(body: SkillCreate):
    store = get_skill_store()
    if await store.get(f"{body.category}/{body.name}"):
        raise HTTPException(409, f"Skill '{body.category}/{body.name}' already exists")
    return await store.create(body)


@router.get("/{category}/{name}", response_model=Skill)
async def get_skill(category: str, name: str):
    store = get_skill_store()
    skill = await store.get(f"{category}/{name}")
    if not skill:
        raise HTTPException(404, "skill not found")
    return skill


@router.patch("/{category}/{name}", response_model=Skill)
async def patch_skill(category: str, name: str, body: SkillPatch):
    store = get_skill_store()
    skill = await store.get(f"{category}/{name}")
    if not skill:
        raise HTTPException(404, "skill not found")
    if skill.source == "builtin" and body.content is not None:
        raise HTTPException(403, "内置技能内容不可修改")
    if skill.locked and body.content is not None:
        raise HTTPException(403, "技能已锁定，无法修改内容")
    return await store.update(f"{category}/{name}", body)


@router.delete("/{category}/{name}", status_code=204)
async def delete_skill(category: str, name: str):
    store = get_skill_store()
    skill = await store.get(f"{category}/{name}")
    if not skill:
        raise HTTPException(404, "skill not found")
    if skill.pinned:
        raise HTTPException(403, "skill is pinned — unpin before deleting")
    await store.delete(f"{category}/{name}")


@router.get("/review_log")
async def get_review_log(limit: int = Query(default=5, ge=1, le=100)):
    store = get_skill_store()
    entries = await store.read_review_log(limit=limit)
    return entries


@router.post("/import/preview", response_model=ImportPreviewResponse)
async def import_preview(
    file: UploadFile = File(...),
    category: str = Form(default="imported"),
):
    store = get_skill_store()
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件过大，最大支持 10 MB")

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


@router.get("/{category}/{name}/files")
async def list_skill_files(category: str, name: str):
    store = get_skill_store()
    if not await store.get(f"{category}/{name}"):
        raise HTTPException(404, "skill not found")
    return {"files": await store.list_files(f"{category}/{name}")}


@router.get("/{category}/{name}/files/{file_path:path}")
async def read_skill_file(category: str, name: str, file_path: str):
    store = get_skill_store()
    try:
        content = await store.read_file(f"{category}/{name}", file_path)
        return {"content": content, "filename": file_path}
    except PermissionError:
        raise HTTPException(403, "access denied")
    except FileNotFoundError:
        raise HTTPException(404, f"file not found: {file_path}")
