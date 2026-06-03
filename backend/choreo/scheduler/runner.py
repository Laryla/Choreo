from __future__ import annotations
import logging
import time
import uuid

from langchain_core.messages import HumanMessage

from choreo.db import SessionLocal, TaskRow, TaskRunRow
from choreo.scheduler.notifiers import NotifierRouter
from choreo.agents.choreo_agent import create_choreo_agent
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def get_task_and_last_run(task_id: str) -> tuple[TaskRow | None, TaskRunRow | None]:
    async with SessionLocal() as db:
        task = (await db.execute(select(TaskRow).where(TaskRow.id == task_id))).scalar_one_or_none()
        if not task:
            return None, None
        last = (await db.execute(
            select(TaskRunRow)
            .where(TaskRunRow.task_id == task_id, TaskRunRow.status == "success")
            .order_by(TaskRunRow.finished_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        return task, last


async def create_run(task_id: str, run_id: str | None = None) -> TaskRunRow:
    async with SessionLocal() as db:
        if run_id:
            run = (await db.execute(select(TaskRunRow).where(TaskRunRow.id == run_id))).scalar_one_or_none()
            if run:
                run.status = "running"
                run.started_at = int(time.time() * 1000)
                await db.commit()
                await db.refresh(run)
                return run
        run = TaskRunRow(
            id=str(uuid.uuid4()),
            task_id=task_id,
            status="running",
            started_at=int(time.time() * 1000),
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run


async def update_run(run_id: str, *, status: str, output: str = "", error: str | None = None) -> None:
    async with SessionLocal() as db:
        run = (await db.execute(select(TaskRunRow).where(TaskRunRow.id == run_id))).scalar_one()
        run.status = status
        run.output = output
        run.error = error
        run.finished_at = int(time.time() * 1000)
        await db.commit()


class TaskRunner:
    async def run(self, task_id: str, run_id: str | None = None) -> None:
        task, last_run = await get_task_and_last_run(task_id)
        if not task:
            logger.error("TaskRunner: task %s not found", task_id)
            return

        run = await create_run(task_id, run_id)
        logger.info("TaskRunner: starting run %s for task %s", run.id, task_id)

        prompt = task.prompt
        if last_run and last_run.output:
            import datetime
            ts = datetime.datetime.fromtimestamp(last_run.finished_at / 1000).strftime("%Y-%m-%d %H:%M")
            prompt += f"\n\n---\n上次运行结果（{ts}）：\n{last_run.output}"

        try:
            agent = create_choreo_agent(headless=True)
            result = await agent.ainvoke({"messages": [HumanMessage(content=prompt)]})
            messages = result.get("messages", [])
            output = ""
            for msg in reversed(messages):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                if content.strip():
                    output = content
                    break
            await update_run(run.id, status="success", output=output)
            run.status = "success"
            run.output = output
            logger.info("TaskRunner: run %s succeeded", run.id)
        except Exception as e:
            logger.exception("TaskRunner: run %s failed", run.id)
            await update_run(run.id, status="failed", error=str(e))
            run.status = "failed"
            run.error = str(e)
            return

        notifier = NotifierRouter()
        await notifier.send(task, run)
