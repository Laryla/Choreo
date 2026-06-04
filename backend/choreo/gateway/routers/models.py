import os
from fastapi import APIRouter
from pydantic import BaseModel

from choreo.config import settings

router = APIRouter()


class ModelInfo(BaseModel):
    name: str
    model: str | None = None
    display_name: str | None = None


@router.get("/", response_model=list[ModelInfo])
async def list_models():
    seen = set()
    result = []
    for m in settings.MODELS:
        name = m.get("name")
        if name and name not in seen:
            seen.add(name)
            result.append(ModelInfo(
                name=name,
                model=m.get("model"),
                display_name=m.get("display_name"),
            ))
    return result


@router.get("/active")
async def get_active_model():
    active = os.getenv("CHOREO_MODEL_NAME") or settings.ACTIVE_MODEL
    return {"active_model": active}
