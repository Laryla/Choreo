import uuid
import time
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from choreo.models.task import Task, TaskCreate, TaskPatch, TaskRun
from choreo.db import SessionLocal, TaskRow, TaskRunRow
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
        prompt=row.prompt,
        script_path=row.script_path,
        notify_config=row.notify_config or {},
        status=row.status,  # type: ignore
    )


def _row_to_run(row: TaskRunRow) -> TaskRun:
    return TaskRun(
        id=row.id,
        task_id=row.task_id,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        output=row.output,
        error=row.error,
    )


@router.get("/", response_model=list[Task])
async def list_tasks(db: AsyncSession = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    result = await db.execute(select(TaskRow).where(TaskRow.user_id == user_id))
    return [_row_to_task(r) for r in result.scalars()]


@router.post("/", response_model=Task, status_code=201)
async def create_task(
    body: TaskCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    row = TaskRow(
        id=str(uuid.uuid4()),
        user_id=user_id,
        description=body.description,
        cron=body.cron,
        prompt=body.prompt,
        script_path=body.script_path,
        notify_config=body.notify_config,
        status="active",
    )
    db.add(row)
    await db.commit()
    scheduler = getattr(request.app.state, "task_scheduler", None)
    if scheduler:
        scheduler.add_task(row.id, row.cron)
    return _row_to_task(row)


@router.patch("/{task_id}", response_model=Task)
async def patch_task(
    task_id: str,
    body: TaskPatch,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskRow).where(TaskRow.id == task_id))
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "task not found")
    if body.status is not None:
        row.status = body.status
        scheduler = getattr(request.app.state, "task_scheduler", None)
        if scheduler:
            if body.status == "paused":
                scheduler.pause_task(task_id)
            else:
                scheduler.resume_task(task_id)
    await db.commit()
    return _row_to_task(row)


@router.delete("/{task_id}", status_code=204)
async def remove_task(task_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(delete(TaskRow).where(TaskRow.id == task_id))
    if result.rowcount == 0:
        raise HTTPException(404, "task not found")
    await db.commit()
    scheduler = getattr(request.app.state, "task_scheduler", None)
    if scheduler:
        scheduler.remove_task(task_id)


@router.get("/{task_id}/runs", response_model=list[TaskRun])
async def list_runs(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TaskRunRow)
        .where(TaskRunRow.task_id == task_id)
        .order_by(TaskRunRow.started_at.desc())
        .limit(20)
    )
    return [_row_to_run(r) for r in result.scalars()]


@router.get("/{task_id}/runs/{run_id}", response_model=TaskRun)
async def get_run(task_id: str, run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TaskRunRow).where(TaskRunRow.id == run_id, TaskRunRow.task_id == task_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(404, "run not found")
    return _row_to_run(row)


@router.post("/{task_id}/runs", response_model=TaskRun, status_code=202)
async def trigger_run(task_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskRow).where(TaskRow.id == task_id))
    if not result.scalar_one_or_none():
        raise HTTPException(404, "task not found")
    import asyncio
    from choreo.scheduler.runner import TaskRunner
    run = TaskRunRow(
        id=str(uuid.uuid4()),
        task_id=task_id,
        status="pending",
        started_at=int(time.time() * 1000),
    )
    db.add(run)
    await db.commit()
    run_id = run.id
    runner = TaskRunner()
    asyncio.create_task(runner.run(task_id, run_id))
    return _row_to_run(run)
