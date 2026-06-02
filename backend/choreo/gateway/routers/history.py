from fastapi import APIRouter
from sqlalchemy import select, func
from choreo.db import SessionLocal, ThreadRow

router = APIRouter()


@router.get("/")
async def list_history(page: int = 1, size: int = 20):
    offset = (page - 1) * size
    async with SessionLocal() as db:
        total_result = await db.execute(select(func.count()).select_from(ThreadRow))
        total = total_result.scalar_one()

        result = await db.execute(
            select(ThreadRow)
            .order_by(ThreadRow.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        rows = result.scalars().all()

    items = [
        {
            "thread_id": r.thread_id,
            "title": r.title or "未命名对话",
            "status": r.status,
            "created_at": r.created_at,
        }
        for r in rows
    ]
    return {"total": total, "page": page, "size": size, "items": items}
