from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from choreo.platforms.base import BaseChatAdapter, MessageEvent, SendResult
from choreo.platforms.registry import platform_registry, PlatformEntry

logger = logging.getLogger(__name__)


def _check_deps() -> bool:
    try:
        import lark_oapi  # noqa: F401
        return True
    except ImportError:
        return False


class FeishuAdapter(BaseChatAdapter):
    """
    Feishu/Lark platform adapter.

    transport=websocket: long-connection via lark_oapi.ws.Client (no public IP needed)
    transport=webhook:   handle_webhook() is called by channel/router.py
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        from choreo.config import settings
        self._app_id = settings.FEISHU_APP_ID
        self._app_secret = settings.FEISHU_APP_SECRET
        self._transport = config.get("transport", "websocket")
        self._bot_open_id = settings.FEISHU_BOT_OPEN_ID
        self._ws_client: Any = None
        self._ws_task: Optional[asyncio.Task] = None
        self._lark_client: Any = None

    def _build_lark_client(self) -> Any:
        import lark_oapi as lark
        if self._lark_client is None:
            self._lark_client = (
                lark.Client.builder()
                .app_id(self._app_id)
                .app_secret(self._app_secret)
                .build()
            )
        return self._lark_client

    async def connect(self) -> None:
        if self._transport == "websocket":
            await self._start_websocket()
        # webhook: route is registered externally via channel/router.py; nothing to start here

    async def disconnect(self) -> None:
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass
        if self._ws_task is not None:
            try:
                await asyncio.wait_for(self._ws_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._ws_task.cancel()

    async def send(self, chat_id: str, text: str) -> SendResult:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )
        client = self._build_lark_client()
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            )
            .build()
        )
        try:
            resp = await asyncio.to_thread(client.im.v1.message.create, request)
            if resp.success():
                return SendResult(success=True)
            return SendResult(success=False, error=f"code={resp.code} msg={resp.msg}")
        except Exception as e:
            logger.exception("[Feishu] send failed")
            return SendResult(success=False, error=str(e))

    async def handle_webhook(self, payload: dict) -> Optional[dict]:
        """Handle incoming Feishu webhook POST body. Returns response dict or None."""
        # URL verification (schema 1.0 and 2.0)
        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        # Event dispatch (schema 2.0)
        header = payload.get("header", {})
        event_type = header.get("event_type", "")
        if event_type == "im.message.receive_v1":
            event_body = payload.get("event", {})
            event = self._parse_message_event(event_body)
            if event:
                await self._dispatch(event)
        return None

    def _parse_message_event(self, event_body: dict) -> Optional[MessageEvent]:
        message = event_body.get("message", {})
        sender = event_body.get("sender", {})

        if message.get("message_type") != "text":
            return None

        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "p2p")
        user_id = (sender.get("sender_id") or {}).get("open_id", "")

        try:
            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            return None

        # Group chat: only respond to @mentions when bot_open_id is configured
        if chat_type != "p2p" and self._bot_open_id:
            mentions = message.get("mentions", [])
            mentioned_ids = [(m.get("id") or {}).get("open_id", "") for m in mentions]
            if self._bot_open_id not in mentioned_ids:
                return None

        if not text:
            return None

        return MessageEvent(
            platform="feishu",
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            raw=event_body,
        )

    async def _start_websocket(self) -> None:
        import lark_oapi as lark

        loop = asyncio.get_running_loop()

        def on_message(data: Any) -> None:
            try:
                msg = data.event
                sender_id = getattr(getattr(getattr(msg, "sender", None), "sender_id", None), "open_id", "") or ""
                message = getattr(msg, "message", None)
                if message is None:
                    return
                event_body = {
                    "sender": {"sender_id": {"open_id": sender_id}},
                    "message": {
                        "chat_id": getattr(message, "chat_id", "") or "",
                        "chat_type": getattr(message, "chat_type", "p2p") or "p2p",
                        "message_type": getattr(message, "message_type", "") or "",
                        "content": getattr(message, "content", "{}") or "{}",
                        "mentions": list(getattr(message, "mentions", []) or []),
                    },
                }
            except Exception:
                logger.exception("[Feishu WS] Failed to extract event body")
                return

            event = self._parse_message_event(event_body)
            if event:
                asyncio.run_coroutine_threadsafe(self._dispatch(event), loop)

        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        self._ws_client = lark.ws.Client(
            self._app_id,
            self._app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.ERROR,
        )
        self._ws_task = asyncio.create_task(
            asyncio.to_thread(self._ws_client.start)
        )
        logger.info("[Feishu] WebSocket long-connection started")


# Self-register in the module-level singleton
platform_registry.register(PlatformEntry(
    name="feishu",
    label="Feishu / Lark",
    adapter_factory=lambda cfg: FeishuAdapter(cfg),
    check_fn=_check_deps,
    required_env=["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
    install_hint="uv add lark-oapi",
))
