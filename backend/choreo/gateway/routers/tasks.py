import uuid
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from choreo.models.task import Task, TaskCreate, TaskPatch
from choreo.db import SessionLocal, TaskRow
from choreo.auth.deps import get_current_user_id

router = APIRouter()


async def get_db():
    async with SessionLocal() as session:
        yield session


def _row_to_task(row: TaskRow) -> Task:
    return Task(
        id=row.id,
        description=row.description,
        cron=row.cron,
        script_path=row.script_path,
        status=row.status,  # type: ignore
    )


@router.get("/", response_model=list[Task])
async def list_tasks(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    result = await db.execute(select(TaskRow).where(TaskRow.user_id == user_id))
    return [_row_to_task(r) for r in result.scalars()]


@router.post("/", response_model=Task, status_code=201)
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    row = TaskRow(id=str(uuid.uuid4()), user_id=user_id, **body.model_dump())
    db.add(row)
    await db.commit()
    return _row_to_task(row)


@router.patch("/{task_id}", response_model=Task)
async def patch_task(task_id: str, body: TaskPatch, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskRow).where(TaskRow.id == task_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "task not found")
    if body.status is not None:
        row.status = body.status
    await db.commit()
    return _row_to_task(row)


@router.delete("/{task_id}", status_code=204)
async def remove_task(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(TaskRow).where(TaskRow.id == task_id))
    if result.rowcount == 0:
        raise HTTPException(404, "task not found")
    await db.commit()
