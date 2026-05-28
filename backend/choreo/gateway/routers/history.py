from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_history(page: int = 1, size: int = 20):
    return {"total": 0, "items": []}
