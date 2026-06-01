from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

MessageHandler = Callable[["MessageEvent"], Awaitable[None]]


@dataclass
class MessageEvent:
    platform: str
    chat_id: str
    user_id: str
    text: str
    raw: Any = None

    @property
    def is_command(self) -> bool:
        return self.text.strip().startswith("/")

    @property
    def command(self) -> Optional[str]:
        if not self.is_command:
            return None
        parts = self.text.strip().split(maxsplit=1)
        return parts[0][1:].lower() if parts else None

    @property
    def command_args(self) -> str:
        if not self.is_command:
            return self.text
        parts = self.text.strip().split(maxsplit=1)
        return parts[1] if len(parts) > 1 else ""


@dataclass
class SendResult:
    success: bool
    error: Optional[str] = None


class BaseChatAdapter(ABC):
    """Abstract base for all chat platform adapters."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self._message_handler: Optional[MessageHandler] = None

    def set_message_handler(self, handler: MessageHandler) -> None:
        self._message_handler = handler

    @abstractmethod
    async def connect(self) -> None:
        """Start WebSocket long-connection or register webhook route."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Stop connection and release resources."""

    @abstractmethod
    async def send(self, chat_id: str, text: str) -> SendResult:
        """Send a reply to a chat."""

    async def _dispatch(self, event: MessageEvent) -> None:
        if self._message_handler:
            try:
                await self._message_handler(event)
            except Exception:
                logger.exception("[%s] Message handler error", self.__class__.__name__)
