# backend/choreo/gateway/routers/skills.py
from fastapi import APIRouter, HTTPException, Query
from choreo.models.skill import Skill, SkillCreate, SkillPatch
from choreo.skills import get_skill_store

router = APIRouter()


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
    if not await store.get(f"{category}/{name}"):
        raise HTTPException(404, "skill not found")
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


@router.get("/{category}/{name}/files")
async def list_skill_files(category: str, name: str):
    store = get_skill_store()
    if not await store.get(f"{category}/{name}"):
        raise HTTPException(404, "skill not found")
    return {"files": await store.list_files(f"{category}/{name}")}
