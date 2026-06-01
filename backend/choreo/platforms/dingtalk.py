from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

from choreo.platforms.base import BaseChatAdapter, MessageEvent, SendResult
from choreo.platforms.registry import platform_registry, PlatformEntry

logger = logging.getLogger(__name__)


def _check_deps() -> bool:
    try:
        import dingtalk_stream  # noqa: F401
        return True
    except ImportError:
        return False


class DingTalkAdapter(BaseChatAdapter):
    """
    DingTalk / 钉钉 platform adapter.

    Uses dingtalk-stream SDK for inbound messages (WebSocket long-connection).
    Replies via the session webhook URL included in each inbound message.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        from choreo.config import settings
        self._client_id = settings.DINGTALK_CLIENT_ID
        self._client_secret = settings.DINGTALK_CLIENT_SECRET
        self._stream_client = None
        self._ws_thread: Optional[threading.Thread] = None
        # chat_id → (webhook_url, expiry_ms)
        self._webhook_cache: dict[str, tuple[str, int]] = {}

    async def connect(self) -> None:
        await self._start_stream()

    async def disconnect(self) -> None:
        if self._stream_client is not None:
            try:
                self._stream_client.stop()
            except Exception:
                pass
        if self._ws_thread is not None:
            self._ws_thread.join(timeout=5.0)

    async def send(self, chat_id: str, text: str) -> SendResult:
        import httpx

        cached = self._webhook_cache.get(chat_id)
        if not cached:
            logger.warning("[DingTalk] No session webhook cached for chat %s", chat_id)
            return SendResult(success=False, error="No session webhook cached")

        webhook_url, expiry_ms = cached
        if int(time.time() * 1000) > expiry_ms - 300_000:
            logger.warning("[DingTalk] Session webhook expired for chat %s", chat_id)
            return SendResult(success=False, error="Session webhook expired")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    webhook_url,
                    json={"msgtype": "text", "text": {"content": text}},
                )
            if resp.status_code == 200:
                return SendResult(success=True)
            return SendResult(success=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.exception("[DingTalk] send failed")
            return SendResult(success=False, error=str(e))

    async def _start_stream(self) -> None:
        import dingtalk_stream

        main_loop = asyncio.get_running_loop()
        adapter = self

        class _Handler(dingtalk_stream.ChatbotHandler):
            async def process(self, callback):
                msg = dingtalk_stream.ChatbotMessage.from_dict(callback.data)

                if msg.session_webhook:
                    expiry = getattr(msg, "session_webhook_expired_time", None) or (
                        int(time.time() * 1000) + 600_000
                    )
                    adapter._webhook_cache[msg.conversation_id] = (msg.session_webhook, expiry)

                event = adapter._parse_message(msg)
                if event:
                    asyncio.run_coroutine_threadsafe(adapter._dispatch(event), main_loop)

                return dingtalk_stream.AckMessage.STATUS_OK, {}

        credential = dingtalk_stream.Credential(self._client_id, self._client_secret)
        self._stream_client = dingtalk_stream.DingTalkStreamClient(credential)
        self._stream_client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            _Handler(),
        )

        def _run() -> None:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            self._stream_client.start_forever()

        self._ws_thread = threading.Thread(target=_run, daemon=True, name="dingtalk-ws")
        self._ws_thread.start()
        logger.info("[DingTalk] Stream long-connection started")

    def _parse_message(self, msg) -> Optional[MessageEvent]:
        text = ""
        if hasattr(msg, "text") and msg.text:
            text = (getattr(msg.text, "content", "") or "").strip()
        if not text:
            return None
        return MessageEvent(
            platform="dingtalk",
            chat_id=getattr(msg, "conversation_id", "") or "",
            user_id=getattr(msg, "sender_id", "") or "",
            text=text,
            raw=msg,
        )


# Self-register in the module-level singleton
platform_registry.register(PlatformEntry(
    name="dingtalk",
    label="DingTalk / 钉钉",
    adapter_factory=lambda cfg: DingTalkAdapter(cfg),
    check_fn=_check_deps,
    required_env=["DINGTALK_CLIENT_ID", "DINGTALK_CLIENT_SECRET"],
    install_hint="uv add dingtalk-stream",
))
