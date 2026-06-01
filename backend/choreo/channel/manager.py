from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from choreo.db import SessionLocal, ChannelRow, ThreadRow
from choreo.platforms.base import BaseChatAdapter, MessageEvent

logger = logging.getLogger(__name__)


class ChannelManager:
    """Routes incoming platform messages to the Choreo agent and back."""

    def __init__(self) -> None:
        self._adapters: dict[str, BaseChatAdapter] = {}

    def register_adapter(self, platform: str, adapter: BaseChatAdapter) -> None:
        self._adapters[platform] = adapter
        adapter.set_message_handler(self.handle)
        logger.info("Registered adapter for platform: %s", platform)

    def get_adapter(self, platform: str) -> Optional[BaseChatAdapter]:
        return self._adapters.get(platform)

    async def start_all(self) -> None:
        for platform, adapter in self._adapters.items():
            try:
                await adapter.connect()
                logger.info("Platform connected: %s", platform)
            except Exception:
                logger.exception("Failed to connect platform: %s", platform)

    async def stop_all(self) -> None:
        for platform, adapter in self._adapters.items():
            try:
                await adapter.disconnect()
            except Exception:
                logger.exception("Failed to disconnect platform: %s", platform)

    async def handle(self, event: MessageEvent) -> None:
        """Entry point for all incoming platform messages."""
        try:
            if event.is_command and event.command in ("new", "reset"):
                await self._handle_new_command(event)
                return
            thread_id = await self._get_or_create_thread_id(event)
            reply = await self._call_agent(thread_id, event.text)
            if reply:
                adapter = self._adapters.get(event.platform)
                if adapter:
                    await adapter.send(event.chat_id, reply)
        except Exception:
            logger.exception("[%s] Error handling message from %s", event.platform, event.chat_id)

    async def notify(self, platform: str, chat_id: str, text: str) -> None:
        """Push a notification to a platform chat (outbound)."""
        adapter = self._adapters.get(platform)
        if adapter:
            await adapter.send(chat_id, text)
        else:
            logger.warning("notify: no adapter for platform '%s'", platform)

    # ── Internal helpers ────────────────────────────────────────────

    async def _handle_new_command(self, event: MessageEvent) -> None:
        new_tid = await self._create_thread()
        await self._save_channel(event.platform, event.chat_id, new_tid, event.user_id)
        adapter = self._adapters.get(event.platform)
        if adapter:
            await adapter.send(event.chat_id, "已开启新对话 ✨")

    async def _get_or_create_thread_id(self, event: MessageEvent) -> str:
        async with SessionLocal() as db:
            result = await db.execute(
                select(ChannelRow).where(
                    ChannelRow.platform == event.platform,
                    ChannelRow.chat_id == event.chat_id,
                )
            )
            row = result.scalar_one_or_none()

        if row:
            return row.thread_id

        thread_id = await self._create_thread()
        await self._save_channel(event.platform, event.chat_id, thread_id, event.user_id)
        return thread_id

    async def _create_thread(self) -> str:
        thread_id = str(uuid.uuid4())
        now = int(time.time())
        async with SessionLocal() as db:
            db.add(ThreadRow(thread_id=thread_id, status="idle", created_at=now))
            await db.commit()
        return thread_id

    async def _save_channel(
        self, platform: str, chat_id: str, thread_id: str, user_id: Optional[str]
    ) -> None:
        now = int(time.time())
        async with SessionLocal() as db:
            stmt = (
                insert(ChannelRow)
                .values(
                    platform=platform,
                    chat_id=chat_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    constraint="uq_channel_platform_chat",
                    set_={"thread_id": thread_id, "user_id": user_id, "updated_at": now},
                )
            )
            await db.execute(stmt)
            await db.commit()

    async def _call_agent(self, thread_id: str, text: str) -> str:
        from choreo.agents import get_agent
        from langchain_core.messages import AIMessageChunk

        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [{"role": "user", "content": text}]}
        chunks: list[str] = []

        async for event in get_agent().astream(
            inputs,
            config=config,
            stream_mode=["messages"],
            version="v2",
        ):
            if event.get("type") == "messages":
                token, _ = event["data"]
                if isinstance(token, AIMessageChunk):
                    content = token.content
                    if isinstance(content, str):
                        chunks.append(content)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                chunks.append(block.get("text", ""))

        return "".join(chunks)
