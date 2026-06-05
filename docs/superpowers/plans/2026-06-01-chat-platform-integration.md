# Chat Platform Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pluggable chat platform adapter layer to Choreo so Feishu (and future platforms) can send messages to the Choreo agent and receive replies, with persistent chat_id → thread_id mapping.

**Architecture:** An independent `platforms/` layer defines `BaseChatAdapter` ABC and a `PlatformRegistry` for self-registration. A `ChannelManager` owns chat_id → thread_id mapping and drives the agent call. Feishu supports both WebSocket (no public IP) and Webhook (public IP) transports, configured in `config.yaml`.

**Tech Stack:** Python, FastAPI, SQLAlchemy async, `lark-oapi` (Feishu SDK), `pytest-asyncio`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/choreo/db.py` | Modify | Add `ChannelRow` table |
| `backend/choreo/config.py` | Modify | Add Feishu transport + webhook env vars |
| `backend/config.yaml` | Modify | Add `platforms:` block |
| `backend/pyproject.toml` | Modify | Add `lark-oapi` dependency |
| `backend/choreo/platforms/__init__.py` | Create | Re-exports |
| `backend/choreo/platforms/base.py` | Create | `BaseChatAdapter` ABC + `MessageEvent` |
| `backend/choreo/platforms/registry.py` | Create | `PlatformRegistry` singleton |
| `backend/choreo/platforms/feishu.py` | Create | `FeishuAdapter` (WebSocket + Webhook) |
| `backend/choreo/channel/__init__.py` | Create | Re-exports |
| `backend/choreo/channel/manager.py` | Create | `ChannelManager` — message routing + thread mapping |
| `backend/choreo/channel/router.py` | Create | FastAPI webhook router `/channels/{platform}/webhook` |
| `backend/choreo/gateway/app.py` | Modify | Lifespan + router registration |
| `backend/tests/test_channel_manager.py` | Create | Unit tests for ChannelManager |
| `backend/tests/test_feishu_webhook.py` | Create | Unit tests for Feishu webhook handling |

---

## Task 1: Add ChannelRow to db.py and Feishu config fields

**Files:**
- Modify: `backend/choreo/db.py`
- Modify: `backend/choreo/config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_channel_row.py`:
```python
import pytest
from choreo.db import ChannelRow, Base

def test_channel_row_has_required_columns():
    cols = {c.key for c in ChannelRow.__table__.columns}
    assert "platform" in cols
    assert "chat_id" in cols
    assert "thread_id" in cols
    assert "user_id" in cols
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_channel_row.py -v
```
Expected: `ImportError` or `AttributeError: module 'choreo.db' has no attribute 'ChannelRow'`

- [ ] **Step 3: Add ChannelRow to db.py**

In `backend/choreo/db.py`, add after the `UserRow` class and before `init_db()`:

```python
class ChannelRow(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time()))
    updated_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint("platform", "chat_id", name="uq_channel_platform_chat"),
    )
```

- [ ] **Step 4: Add new Feishu fields to config.py**

In `backend/choreo/config.py`, add after the existing `FEISHU_APP_SECRET` line:

```python
    # 飞书 Bot（平台接入）
    FEISHU_TRANSPORT: str = "websocket"          # websocket | webhook
    FEISHU_ENCRYPT_KEY: str = ""                  # webhook 模式：加密 key
    FEISHU_VERIFICATION_TOKEN: str = ""           # webhook 模式：校验 token
    FEISHU_BOT_OPEN_ID: str = ""                  # 群聊 @mention 过滤用
    FEISHU_ENABLED: bool = False                  # 显式开启才启动
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_channel_row.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/db.py backend/choreo/config.py backend/tests/test_channel_row.py
git commit -m "feat(channel): add ChannelRow table and Feishu config fields"
```

---

## Task 2: Create platforms/base.py

**Files:**
- Create: `backend/choreo/platforms/__init__.py`
- Create: `backend/choreo/platforms/base.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_platform_base.py`:
```python
from choreo.platforms.base import MessageEvent

def test_message_event_is_command():
    event = MessageEvent(platform="feishu", chat_id="c1", user_id="u1", text="/new")
    assert event.is_command is True
    assert event.command == "new"

def test_message_event_not_command():
    event = MessageEvent(platform="feishu", chat_id="c1", user_id="u1", text="hello world")
    assert event.is_command is False
    assert event.command is None

def test_message_event_command_args():
    event = MessageEvent(platform="feishu", chat_id="c1", user_id="u1", text="/skill foo bar")
    assert event.command == "skill"
    assert event.command_args == "foo bar"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_platform_base.py -v
```
Expected: `ModuleNotFoundError: No module named 'choreo.platforms'`

- [ ] **Step 3: Create platforms/__init__.py**

```python
# backend/choreo/platforms/__init__.py
from choreo.platforms.base import BaseChatAdapter, MessageEvent, SendResult
from choreo.platforms.registry import platform_registry, PlatformEntry

__all__ = ["BaseChatAdapter", "MessageEvent", "SendResult", "platform_registry", "PlatformEntry"]
```

- [ ] **Step 4: Create platforms/base.py**

```python
# backend/choreo/platforms/base.py
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

    def __init__(self, config: dict):
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
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_platform_base.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/platforms/ backend/tests/test_platform_base.py
git commit -m "feat(platforms): add BaseChatAdapter ABC and MessageEvent"
```

---

## Task 3: Create platforms/registry.py

**Files:**
- Create: `backend/choreo/platforms/registry.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_platform_base.py`:
```python
from choreo.platforms.registry import PlatformRegistry, PlatformEntry
from choreo.platforms.base import BaseChatAdapter, SendResult

class _FakeAdapter(BaseChatAdapter):
    async def connect(self): pass
    async def disconnect(self): pass
    async def send(self, chat_id, text): return SendResult(success=True)

def test_registry_register_and_create():
    reg = PlatformRegistry()
    reg.register(PlatformEntry(
        name="fake",
        label="Fake",
        adapter_factory=lambda cfg: _FakeAdapter(cfg),
        check_fn=lambda: True,
        required_env=[],
    ))
    adapter = reg.create_adapter("fake", {})
    assert isinstance(adapter, _FakeAdapter)

def test_registry_missing_deps_returns_none():
    reg = PlatformRegistry()
    reg.register(PlatformEntry(
        name="missing",
        label="Missing",
        adapter_factory=lambda cfg: _FakeAdapter(cfg),
        check_fn=lambda: False,
        required_env=[],
    ))
    assert reg.create_adapter("missing", {}) is None

def test_registry_unknown_platform_returns_none():
    reg = PlatformRegistry()
    assert reg.create_adapter("nope", {}) is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_platform_base.py::test_registry_register_and_create -v
```
Expected: `ImportError`

- [ ] **Step 3: Create platforms/registry.py**

```python
# backend/choreo/platforms/registry.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class PlatformEntry:
    name: str
    label: str
    adapter_factory: Callable[[dict], Any]
    check_fn: Callable[[], bool]
    required_env: list[str] = field(default_factory=list)
    install_hint: str = ""


class PlatformRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, PlatformEntry] = {}

    def register(self, entry: PlatformEntry) -> None:
        self._entries[entry.name] = entry
        logger.debug("Registered platform adapter: %s", entry.name)

    def get(self, name: str) -> Optional[PlatformEntry]:
        return self._entries.get(name)

    def all_names(self) -> list[str]:
        return list(self._entries.keys())

    def create_adapter(self, name: str, config: dict) -> Optional[Any]:
        entry = self._entries.get(name)
        if entry is None:
            return None
        if not entry.check_fn():
            hint = f" ({entry.install_hint})" if entry.install_hint else ""
            logger.warning("Platform '%s' requirements not met%s", entry.label, hint)
            return None
        try:
            return entry.adapter_factory(config)
        except Exception:
            logger.exception("Failed to create adapter for platform '%s'", entry.label)
            return None

    def load_from_config(self, platforms_config: list[dict]) -> list[Any]:
        adapters = []
        for cfg in platforms_config:
            name = cfg.get("name", "")
            adapter = self.create_adapter(name, cfg)
            if adapter is not None:
                adapters.append(adapter)
        return adapters


# Module-level singleton — adapters self-register at import time
platform_registry = PlatformRegistry()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_platform_base.py -v
```
Expected: PASS (all 6 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/platforms/registry.py
git commit -m "feat(platforms): add PlatformRegistry with self-registration"
```

---

## Task 4: Create channel/manager.py

**Files:**
- Create: `backend/choreo/channel/__init__.py`
- Create: `backend/choreo/channel/manager.py`
- Create: `backend/tests/test_channel_manager.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_channel_manager.py`:
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from choreo.channel.manager import ChannelManager
from choreo.platforms.base import BaseChatAdapter, MessageEvent, SendResult


class FakeAdapter(BaseChatAdapter):
    def __init__(self):
        super().__init__({})
        self.sent: list[tuple[str, str]] = []

    async def connect(self): pass
    async def disconnect(self): pass
    async def send(self, chat_id: str, text: str) -> SendResult:
        self.sent.append((chat_id, text))
        return SendResult(success=True)


@pytest.fixture
def adapter():
    return FakeAdapter()


@pytest.fixture
def manager(adapter):
    mgr = ChannelManager()
    mgr.register_adapter("feishu", adapter)
    return mgr


@pytest.mark.asyncio
async def test_handle_new_command_creates_new_thread(manager, adapter):
    event = MessageEvent(platform="feishu", chat_id="chat_001", user_id="user_1", text="/new")
    with patch.object(manager, "_get_or_create_thread_id", new_callable=AsyncMock, return_value="tid_old") as mock_get, \
         patch.object(manager, "_create_thread", new_callable=AsyncMock, return_value="tid_new") as mock_create, \
         patch.object(manager, "_save_channel", new_callable=AsyncMock) as mock_save:
        await manager.handle(event)
        mock_create.assert_called_once()
        mock_save.assert_called_once_with("feishu", "chat_001", "tid_new", "user_1")
    # Should reply with confirmation
    assert len(adapter.sent) == 1
    assert "新对话" in adapter.sent[0][1] or "new" in adapter.sent[0][1].lower()


@pytest.mark.asyncio
async def test_handle_message_routes_to_agent(manager, adapter):
    event = MessageEvent(platform="feishu", chat_id="chat_001", user_id="user_1", text="hello")
    with patch.object(manager, "_get_or_create_thread_id", new_callable=AsyncMock, return_value="tid_123"), \
         patch.object(manager, "_call_agent", new_callable=AsyncMock, return_value="hi there") as mock_agent:
        await manager.handle(event)
        mock_agent.assert_called_once_with("tid_123", "hello")
    assert adapter.sent == [("chat_001", "hi there")]


@pytest.mark.asyncio
async def test_notify_sends_to_adapter(manager, adapter):
    await manager.notify("feishu", "chat_001", "task done")
    assert adapter.sent == [("chat_001", "task done")]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_channel_manager.py -v
```
Expected: `ModuleNotFoundError: No module named 'choreo.channel'`

- [ ] **Step 3: Create channel/__init__.py**

```python
# backend/choreo/channel/__init__.py
from choreo.channel.manager import ChannelManager

__all__ = ["ChannelManager"]
```

- [ ] **Step 4: Create channel/manager.py**

```python
# backend/choreo/channel/manager.py
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select, update
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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_channel_manager.py -v
```
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/channel/ backend/tests/test_channel_manager.py
git commit -m "feat(channel): add ChannelManager with thread mapping and agent routing"
```

---

## Task 5: Create channel/router.py (webhook endpoint)

**Files:**
- Create: `backend/choreo/channel/router.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_feishu_webhook.py`:
```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from choreo.channel.router import make_channel_router


@pytest.fixture
def app():
    manager = MagicMock()
    manager.get_adapter = MagicMock(return_value=None)
    test_app = FastAPI()
    test_app.include_router(make_channel_router(manager))
    return test_app


def test_webhook_unknown_platform_returns_404(app):
    client = TestClient(app)
    resp = client.post("/channels/unknown/webhook", json={})
    assert resp.status_code == 404


def test_webhook_returns_200_for_known_platform():
    from choreo.platforms.base import BaseChatAdapter, SendResult

    class FakeAdapter(BaseChatAdapter):
        def __init__(self):
            super().__init__({})
            self.webhook_calls = []
        async def connect(self): pass
        async def disconnect(self): pass
        async def send(self, chat_id, text): return SendResult(success=True)
        async def handle_webhook(self, payload: dict): self.webhook_calls.append(payload)

    adapter = FakeAdapter()
    manager = MagicMock()
    manager.get_adapter = MagicMock(return_value=adapter)

    test_app = FastAPI()
    test_app.include_router(make_channel_router(manager))
    client = TestClient(test_app)
    resp = client.post("/channels/feishu/webhook", json={"type": "url_verification", "challenge": "abc"})
    assert resp.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_feishu_webhook.py -v
```
Expected: `ImportError`

- [ ] **Step 3: Create channel/router.py**

```python
# backend/choreo/channel/router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from choreo.channel.manager import ChannelManager


def make_channel_router(channel_manager: "ChannelManager") -> APIRouter:
    router = APIRouter(prefix="/channels", tags=["channels"])

    @router.post("/{platform}/webhook")
    async def platform_webhook(platform: str, request: Request):
        adapter = channel_manager.get_adapter(platform)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"Platform '{platform}' not found")
        payload = await request.json()
        # Delegate to adapter's webhook handler (must implement handle_webhook)
        if hasattr(adapter, "handle_webhook"):
            result = await adapter.handle_webhook(payload)
            if result is not None:
                return result
        return {"ok": True}

    return router
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_feishu_webhook.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/channel/router.py backend/tests/test_feishu_webhook.py
git commit -m "feat(channel): add webhook router factory"
```

---

## Task 6: Add lark-oapi dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add lark-oapi to pyproject.toml**

In `backend/pyproject.toml`, add `"lark-oapi>=1.3"` to the `dependencies` list:

```toml
dependencies = [
    ...existing deps...,
    "lark-oapi>=1.3",
]
```

- [ ] **Step 2: Install the dependency**

```bash
cd backend && uv sync
```
Expected: `lark-oapi` appears in the lock/installed packages without errors.

- [ ] **Step 3: Verify import works**

```bash
cd backend && uv run python -c "import lark_oapi; print('lark_oapi OK', lark_oapi.__version__)"
```
Expected: `lark_oapi OK 1.x.x`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore: add lark-oapi dependency for Feishu integration"
```

---

## Task 7: Create platforms/feishu.py

**Files:**
- Create: `backend/choreo/platforms/feishu.py`

This adapter supports two transports:
- **WebSocket**: uses `lark_oapi.ws.Client` (blocking, wrapped in `asyncio.to_thread`)
- **Webhook**: implements `handle_webhook()` called by `channel/router.py`

- [ ] **Step 1: Write failing test for webhook message parsing**

Add to `backend/tests/test_feishu_webhook.py`:
```python
from choreo.platforms.feishu import FeishuAdapter

@pytest.mark.asyncio
async def test_feishu_handle_webhook_url_verification():
    adapter = FeishuAdapter({"transport": "webhook"})
    calls = []
    adapter.set_message_handler(lambda e: calls.append(e) or _noop())
    result = await adapter.handle_webhook({
        "type": "url_verification",
        "challenge": "test_challenge_abc",
    })
    assert result == {"challenge": "test_challenge_abc"}
    assert calls == []  # No message event fired


async def _noop(): pass


@pytest.mark.asyncio
async def test_feishu_handle_webhook_text_message():
    adapter = FeishuAdapter({"transport": "webhook"})
    calls = []
    async def handler(event):
        calls.append(event)
    adapter.set_message_handler(handler)

    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user1"}},
            "message": {
                "chat_id": "oc_chat1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": '{"text": "hello feishu"}',
                "message_id": "om_msg1",
            },
        },
    }
    await adapter.handle_webhook(payload)
    assert len(calls) == 1
    assert calls[0].text == "hello feishu"
    assert calls[0].chat_id == "oc_chat1"
    assert calls[0].user_id == "ou_user1"
    assert calls[0].platform == "feishu"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_feishu_webhook.py::test_feishu_handle_webhook_url_verification -v
```
Expected: `ImportError` or similar

- [ ] **Step 3: Create platforms/feishu.py**

```python
# backend/choreo/platforms/feishu.py
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
    transport=webhook:   FastAPI endpoint handles incoming POST requests
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

    def _build_lark_client(self):
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
        # webhook: route is registered externally via channel/router.py; nothing to start

    async def disconnect(self) -> None:
        if self._ws_client is not None:
            try:
                self._ws_client.stop()
            except Exception:
                pass
        if self._ws_task is not None:
            try:
                await asyncio.wait_for(self._ws_task, timeout=5)
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
            logger.exception("[Feishu] send failed: %s", e)
            return SendResult(success=False, error=str(e))

    async def handle_webhook(self, payload: dict) -> Optional[dict]:
        """Handle incoming Feishu webhook POST body. Returns response dict or None."""
        # URL verification
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

        msg_type = message.get("message_type", "")
        if msg_type != "text":
            return None  # Only text messages supported in v1

        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "p2p")
        user_id = (sender.get("sender_id") or {}).get("open_id", "")

        try:
            content = json.loads(message.get("content", "{}"))
            text = content.get("text", "").strip()
        except (json.JSONDecodeError, AttributeError):
            return None

        # Group chat: only respond to @mentions
        if chat_type != "p2p" and self._bot_open_id:
            mentions = message.get("mentions", [])
            mentioned_ids = [(m.get("id") or {}).get("open_id", "") for m in mentions]
            if self._bot_open_id not in mentioned_ids:
                return None
            # Strip @bot mention from text
            text = text.replace(f"@_user_1", "").strip()

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

        def on_message(data) -> None:
            event_body = {}
            try:
                if hasattr(data, "event"):
                    msg = data.event
                    event_body = {
                        "sender": {"sender_id": {"open_id": getattr(getattr(msg, "sender", None), "sender_id", None) and msg.sender.sender_id.open_id or ""}},
                        "message": {
                            "chat_id": getattr(msg.message, "chat_id", "") if hasattr(msg, "message") else "",
                            "chat_type": getattr(msg.message, "chat_type", "p2p") if hasattr(msg, "message") else "p2p",
                            "message_type": getattr(msg.message, "message_type", "") if hasattr(msg, "message") else "",
                            "content": getattr(msg.message, "content", "{}") if hasattr(msg, "message") else "{}",
                            "mentions": list(getattr(msg.message, "mentions", []) or []) if hasattr(msg, "message") else [],
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_feishu_webhook.py -v
```
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/choreo/platforms/feishu.py
git commit -m "feat(platforms): add FeishuAdapter with WebSocket and Webhook support"
```

---

## Task 8: Wire up in gateway/app.py and config.yaml

**Files:**
- Modify: `backend/choreo/gateway/app.py`
- Modify: `backend/config.yaml`
- Update: `backend/choreo/channel/__init__.py` (re-export router factory)

- [ ] **Step 1: Update channel/__init__.py to export router factory**

```python
# backend/choreo/channel/__init__.py
from choreo.channel.manager import ChannelManager
from choreo.channel.router import make_channel_router

__all__ = ["ChannelManager", "make_channel_router"]
```

- [ ] **Step 2: Add platforms block to config.yaml**

In `backend/config.yaml`, add after the `curator:` block:

```yaml
# 聊天平台接入配置
# transport: websocket（不需要公网） 或 webhook（需要公网地址）
platforms: []
# 示例（需同时在 .env 设置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_ENABLED=true）:
# platforms:
#   - name: feishu
#     transport: websocket
```

- [ ] **Step 3: Modify gateway/app.py lifespan**

Add the following imports at the top of `backend/choreo/gateway/app.py`:

```python
from choreo.channel import ChannelManager, make_channel_router
from choreo.config import settings
```

Inside the `lifespan` function, after the `# 0. 初始化 SkillStore` block and before `# 1. 建表`, add:

```python
    # 0c. 导入平台适配器（触发自注册）
    from choreo.platforms import platform_registry
    if settings.FEISHU_ENABLED:
        import choreo.platforms.feishu  # noqa: F401 — triggers self-registration
```

Then inside the `async with AsyncPostgresSaver...` block, before `yield`, add:

```python
        # 6. 初始化 ChannelManager，连接聊天平台
        _platforms_cfg = _cfg.get("platforms") or []
        channel_manager = ChannelManager()
        app.state.channel_manager = channel_manager
        if _platforms_cfg and settings.FEISHU_ENABLED:
            _adapters = platform_registry.load_from_config(_platforms_cfg)
            for _adapter in _adapters:
                from choreo.platforms.base import BaseChatAdapter
                if isinstance(_adapter, BaseChatAdapter):
                    channel_manager.register_adapter(
                        _adapter._config.get("name", "unknown"), _adapter
                    )
            await channel_manager.start_all()

        yield

        # Cleanup: stop platform adapters
        await channel_manager.stop_all()
```

Remove the bare `yield` that was already there (replace it with the block above).

- [ ] **Step 4: Register the webhook router**

After the existing `app.include_router(...)` calls in `gateway/app.py`, add:

```python
# Channel webhook endpoints (no auth — Feishu verifies via signature)
_channel_manager_placeholder = ChannelManager()
app.include_router(make_channel_router(_channel_manager_placeholder), tags=["channels"])
```

Note: The actual `channel_manager` with connected adapters lives in `app.state.channel_manager`. Update the router factory to use `app.state` at request time instead of a fixed reference.

Update `channel/router.py` to accept the app state dynamically:

```python
# backend/choreo/channel/router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request


def make_channel_router() -> APIRouter:
    router = APIRouter(prefix="/channels", tags=["channels"])

    @router.post("/{platform}/webhook")
    async def platform_webhook(platform: str, request: Request):
        channel_manager = getattr(request.app.state, "channel_manager", None)
        if channel_manager is None:
            raise HTTPException(status_code=503, detail="Channel manager not initialized")
        adapter = channel_manager.get_adapter(platform)
        if adapter is None:
            raise HTTPException(status_code=404, detail=f"Platform '{platform}' not connected")
        payload = await request.json()
        if hasattr(adapter, "handle_webhook"):
            result = await adapter.handle_webhook(payload)
            if result is not None:
                return result
        return {"ok": True}

    return router
```

Update `channel/__init__.py`:
```python
from choreo.channel.manager import ChannelManager
from choreo.channel.router import make_channel_router

__all__ = ["ChannelManager", "make_channel_router"]
```

Update `gateway/app.py` include_router call to use the no-arg form:
```python
app.include_router(make_channel_router(), tags=["channels"])
```

Update `test_feishu_webhook.py` fixture to match the new signature — the router now reads `app.state.channel_manager`, so:
```python
@pytest.fixture
def app():
    from choreo.channel.manager import ChannelManager
    test_app = FastAPI()
    test_app.state.channel_manager = ChannelManager()
    test_app.include_router(make_channel_router())
    return test_app
```

- [ ] **Step 5: Run all tests**

```bash
cd backend && uv run pytest tests/ -v --ignore=tests/test_agent_langsmith.py
```
Expected: All tests PASS (the langsmith test requires API keys, skip it)

- [ ] **Step 6: Commit**

```bash
git add backend/choreo/gateway/app.py backend/choreo/channel/ backend/config.yaml backend/tests/
git commit -m "feat(gateway): wire ChannelManager and platform adapters into FastAPI lifespan"
```

---

## Task 9: Smoke test — enable Feishu WebSocket and verify startup

**Prerequisites:** Have valid `FEISHU_APP_ID` and `FEISHU_APP_SECRET` in `.env`, set `FEISHU_ENABLED=true` and `FEISHU_TRANSPORT=websocket`.

- [ ] **Step 1: Update .env**

Add to `backend/.env`:
```
FEISHU_ENABLED=true
FEISHU_TRANSPORT=websocket
FEISHU_APP_ID=<your app id>
FEISHU_APP_SECRET=<your app secret>
```

- [ ] **Step 2: Update config.yaml platforms block**

```yaml
platforms:
  - name: feishu
    transport: websocket
```

- [ ] **Step 3: Start the server and check logs**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload
```

Expected log output includes:
```
Registered platform adapter: feishu
Platform connected: feishu
[Feishu] WebSocket long-connection started
```

- [ ] **Step 4: Send a test message in Feishu DM**

Send any text message to the bot in a Feishu DM. Expected: the bot replies with the agent's response.

- [ ] **Step 5: Test /new command**

Send `/new` in the same DM. Expected: bot replies "已开启新对话 ✨".

Send another message. Expected: the reply comes from a fresh conversation context (no memory of the previous exchange).

---

## Summary

After all tasks complete:

- `POST /channels/feishu/webhook` handles Feishu Webhook mode events
- WebSocket long-connection auto-starts when `FEISHU_ENABLED=true` and `transport=websocket`
- Every Feishu DM / @mention group message is routed to the Choreo agent via `ChannelManager`
- `chat_id → thread_id` persisted in `channels` table — conversation history survives restarts
- `/new` or `/reset` command creates a fresh thread
- Adding a new platform = one new file in `platforms/` + register in `platform_registry`
