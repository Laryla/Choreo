from pathlib import Path
import yaml
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"


class ModelInfo(BaseModel):
    name: str
    model: str | None = None
    display_name: str | None = None


@router.get("/", response_model=list[ModelInfo])
async def list_models():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    seen = set()
    result = []
    for m in cfg.get("models", []):
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
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    import os
    active = os.getenv("CHOREO_MODEL_NAME") or cfg.get("active_model", "")
    return {"active_model": active}
