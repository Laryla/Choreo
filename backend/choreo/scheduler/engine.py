from __future__ import annotations
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from choreo.db import SessionLocal, TaskRow
from sqlalchemy import select

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        from choreo.scheduler.runner import TaskRunner
        runner = TaskRunner()

        async with SessionLocal() as db:
            rows = (await db.execute(select(TaskRow).where(TaskRow.status == "active"))).scalars().all()

        for row in rows:
            self._register(row.id, row.cron, runner)
            logger.info("Scheduler: registered task %s (%s)", row.id, row.cron)

        self._scheduler.start()
        logger.info("Scheduler started with %d task(s)", len(rows))

    def _register(self, task_id: str, cron: str, runner) -> None:
        try:
            trigger = CronTrigger.from_crontab(cron)
        except Exception as e:
            logger.warning("Invalid cron %r for task %s: %s", cron, task_id, e)
            return
        self._scheduler.add_job(
            runner.run,
            trigger=trigger,
            args=[task_id],
            id=task_id,
            replace_existing=True,
        )

    def add_task(self, task_id: str, cron: str) -> None:
        from choreo.scheduler.runner import TaskRunner
        self._register(task_id, cron, TaskRunner())

    def remove_task(self, task_id: str) -> None:
        try:
            self._scheduler.remove_job(task_id)
        except Exception:
            pass

    def pause_task(self, task_id: str) -> None:
        try:
            self._scheduler.pause_job(task_id)
        except Exception:
            pass

    def resume_task(self, task_id: str) -> None:
        try:
            self._scheduler.resume_job(task_id)
        except Exception:
            pass

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
