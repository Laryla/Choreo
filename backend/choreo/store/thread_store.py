import time
from sqlalchemy import select, update
from choreo.models.thread import Thread, ThreadState
from choreo.db import SessionLocal, ThreadRow


class ThreadStore:
    async def save(self, thread: Thread) -> ThreadState:
        async with SessionLocal() as db:
            row = ThreadRow(
                thread_id=thread.thread_id,
                status="idle",
                created_at=int(time.time()),
            )
            db.add(row)
            await db.commit()
        return ThreadState(thread_id=thread.thread_id)

    async def get(self, thread_id: str) -> ThreadState | None:
        async with SessionLocal() as db:
            result = await db.execute(
                select(ThreadRow).where(ThreadRow.thread_id == thread_id)
            )
            row = result.scalar_one_or_none()
        if not row:
            return None
        return ThreadState(thread_id=row.thread_id, status=row.status, title=row.title)

    async def set_status(self, thread_id: str, status: str) -> None:
        async with SessionLocal() as db:
            await db.execute(
                update(ThreadRow)
                .where(ThreadRow.thread_id == thread_id)
                .values(status=status)
            )
            await db.commit()

    async def get_title(self, thread_id: str) -> str | None:
        async with SessionLocal() as db:
            result = await db.execute(
                select(ThreadRow.title).where(ThreadRow.thread_id == thread_id)
            )
            return result.scalar_one_or_none()

    async def set_title(self, thread_id: str, title: str) -> None:
        async with SessionLocal() as db:
            await db.execute(
                update(ThreadRow)
                .where(ThreadRow.thread_id == thread_id)
                .values(title=title)
            )
            await db.commit()

    async def list_all(self) -> list[ThreadState]:
        async with SessionLocal() as db:
            result = await db.execute(
                select(ThreadRow).order_by(ThreadRow.created_at.desc())
            )
            rows = result.scalars().all()
        return [
            ThreadState(thread_id=r.thread_id, status=r.status, title=r.title)
            for r in rows
        ]

    async def list_by_user(self, user_id: str) -> list[ThreadState]:
        async with SessionLocal() as db:
            result = await db.execute(
                select(ThreadRow)
                .where(ThreadRow.user_id == user_id)
                .order_by(ThreadRow.created_at.desc())
            )
            rows = result.scalars().all()
        return [
            ThreadState(thread_id=r.thread_id, status=r.status, title=r.title)
            for r in rows
        ]

    async def create_for_user(self, thread_id: str, user_id: str) -> None:
        """Record thread ownership for an already-created thread."""
        async with SessionLocal() as db:
            existing = await db.get(ThreadRow, thread_id)
            if existing:
                existing.user_id = user_id
            else:
                db.add(ThreadRow(
                    thread_id=thread_id,
                    user_id=user_id,
                    status="idle",
                    created_at=int(__import__("time").time()),
                ))
            await db.commit()


thread_store = ThreadStore()
