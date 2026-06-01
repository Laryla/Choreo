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
        # "platform:chat_id" → thread_id，等待用户 /approve 或 /reject
        self._pending_hitl: dict[str, str] = {}

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
            if event.is_command and event.command == "approve":
                await self._handle_hitl_decision(event, "approve")
                return
            if event.is_command and event.command == "reject":
                await self._handle_hitl_decision(event, "reject")
                return

            thread_id = await self._get_or_create_thread_id(event)
            reply, interrupted = await self._call_agent(thread_id, event.text)
            if interrupted:
                self._pending_hitl[f"{event.platform}:{event.chat_id}"] = thread_id
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

    async def _handle_hitl_decision(self, event: MessageEvent, decision_type: str) -> None:
        key = f"{event.platform}:{event.chat_id}"
        thread_id = self._pending_hitl.pop(key, None)
        adapter = self._adapters.get(event.platform)
        if not thread_id:
            if adapter:
                await adapter.send(event.chat_id, "没有待确认的操作。")
            return
        from choreo.agents.middlewares import store_decision
        store_decision(thread_id, {"decisions": [{"type": decision_type}]})
        reply, interrupted = await self._resume_agent(thread_id)
        if interrupted:
            self._pending_hitl[key] = thread_id
        if adapter:
            await adapter.send(event.chat_id, reply or ("已取消。" if decision_type == "reject" else ""))

    async def _resume_agent(self, thread_id: str) -> tuple[str, bool]:
        from choreo.agents import get_agent
        from choreo.agents.middlewares import pop_decision
        from langgraph.types import Command
        from langchain_core.messages import AIMessageChunk

        config = {"configurable": {"thread_id": thread_id}}
        decision = pop_decision(thread_id)
        run_input = Command(resume=decision) if decision else Command(resume={"decisions": [{"type": "approve"}]})
        return await self._stream_agent(run_input, config)

    async def _call_agent(self, thread_id: str, text: str) -> tuple[str, bool]:
        from langchain_core.messages import AIMessageChunk  # noqa: F401 (used in _stream_agent)
        config = {"configurable": {"thread_id": thread_id}}
        inputs = {"messages": [{"role": "user", "content": text}]}
        return await self._stream_agent(inputs, config)

    async def _stream_agent(self, run_input, config: dict) -> tuple[str, bool]:
        """Run agent, auto-approve all HITL interrupts, return (reply_text, False)."""
        from choreo.agents import get_agent
        from choreo.agents.middlewares import store_decision, pop_decision
        from langgraph.types import Command
        from langchain_core.messages import AIMessageChunk

        chunks: list[str] = []
        current_input = run_input

        while True:
            interrupted = False
            async for event in get_agent().astream(
                current_input,
                config=config,
                stream_mode=["messages", "updates"],
                version="v2",
            ):
                event_type = event.get("type")
                if event_type == "messages":
                    token, _ = event["data"]
                    if isinstance(token, AIMessageChunk):
                        content = token.content
                        if isinstance(content, str):
                            chunks.append(content)
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    chunks.append(block.get("text", ""))
                elif event_type == "updates" and "__interrupt__" in (event.get("data") or {}):
                    interrupted = True
                    # count how many tool calls need approving
                    pending_count = 0
                    for item in (event["data"]["__interrupt__"] or []):
                        value = item.value if hasattr(item, "value") else (item.get("value", {}) if isinstance(item, dict) else {})
                        pending_count += len(value.get("action_requests") or [])
                    pending_count = max(pending_count, 1)
                    break

            if not interrupted:
                break
            # auto-approve all pending tool calls
            thread_id = config.get("configurable", {}).get("thread_id", "")
            store_decision(thread_id, {"decisions": [{"type": "approve"}] * pending_count})
            decision = pop_decision(thread_id)
            current_input = Command(resume=decision)

        return "".join(chunks), False
