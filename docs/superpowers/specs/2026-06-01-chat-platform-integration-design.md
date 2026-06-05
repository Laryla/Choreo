# Chat Platform Integration Design

**Date:** 2026-06-01  
**Status:** Approved  

## Overview

Add a pluggable chat platform adapter layer to Choreo so external chat services (Feishu, Slack, Discord, etc.) can send messages to the Choreo agent and receive replies. The first implementation targets Feishu; subsequent platforms are added by registering a new adapter without touching core code.

Both directions are supported:
- **Inbound**: platform user sends a message → Choreo agent processes it → reply sent back
- **Outbound**: agent or task result pushes a notification to the platform

## Architecture

### Directory Structure

```
backend/choreo/
├── platforms/
│   ├── __init__.py
│   ├── base.py          # BaseChatAdapter ABC + MessageEvent + SendResult
│   ├── registry.py      # PlatformRegistry (self-registration, no if/elif)
│   └── feishu.py        # FeishuAdapter (first implementation)
├── channel/
│   ├── __init__.py
│   ├── manager.py       # ChannelManager: chat_id → thread_id + message routing
│   └── router.py        # FastAPI router: /channels/{platform}/webhook
└── db.py                # + ChannelRow table
```

### Core Abstractions

**`BaseChatAdapter`** (ABC in `platforms/base.py`):

```python
class BaseChatAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...
    # Start long-polling/websocket connection OR register webhook route

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def send(self, chat_id: str, text: str) -> None: ...
    # Send reply back to the platform

    def set_message_handler(self, handler: Callable[[MessageEvent], Awaitable[None]]) -> None: ...
    # Called by ChannelManager to wire up message routing
```

**`MessageEvent`** (normalized across all platforms):

```python
@dataclass
class MessageEvent:
    platform: str      # "feishu" / "slack" / ...
    chat_id: str       # Platform-side conversation ID
    user_id: str       # Sender's user ID on the platform
    text: str          # Message text
    is_command: bool   # True for /new, /reset, etc.
    raw: Any = None    # Original platform payload (for debugging)
```

**`PlatformRegistry`** (`platforms/registry.py`):

```python
@dataclass
class PlatformEntry:
    name: str                           # "feishu", "slack", ...
    label: str                          # Human-readable label
    adapter_factory: Callable[[dict], BaseChatAdapter]
    check_fn: Callable[[], bool]        # Returns True if deps are available
    required_env: list[str]             # Env vars needed

class PlatformRegistry:
    def register(self, entry: PlatformEntry) -> None: ...
    def create_adapter(self, name: str, config: dict) -> BaseChatAdapter | None: ...
    def load_from_config(self, platforms_config: list[dict]) -> list[BaseChatAdapter]: ...

platform_registry = PlatformRegistry()  # module-level singleton
```

Adapters self-register at import time:
```python
# feishu.py (bottom of file)
platform_registry.register(PlatformEntry(
    name="feishu",
    label="Feishu / Lark",
    adapter_factory=lambda cfg: FeishuAdapter(cfg),
    check_fn=lambda: _check_feishu_deps(),
    required_env=["FEISHU_APP_ID", "FEISHU_APP_SECRET"],
))
```

## Data Flow

```
Platform user sends message
  → FeishuAdapter normalizes → MessageEvent
  → ChannelManager.handle(event)
      → lookup ChannelRow by (platform, chat_id)
      → if /new command or no row: create new Choreo thread
      → POST /threads/{tid}/runs/stream  (reuses existing agent call chain)
      → collect streaming reply
  → FeishuAdapter.send(chat_id, reply_text)
  → Platform user sees reply
```

For **outbound notifications** (agent pushes to platform):
```python
# Any code can do:
await channel_manager.notify(platform="feishu", chat_id="...", text="Task complete!")
```

## Database

New table `ChannelRow` added to `db.py`:

```python
class ChannelRow(Base):
    __tablename__ = "channels"

    id: int (PK)
    platform: str        # "feishu"
    chat_id: str         # Platform-side conversation ID (unique per platform)
    thread_id: str       # Choreo thread_id (FK → threads)
    user_id: str         # Last active user
    created_at: datetime
    updated_at: datetime

    # Unique constraint: (platform, chat_id)
```

## Feishu Adapter

### Transport Modes

Configured via `config.yaml`. Both modes produce identical `MessageEvent` objects.

**WebSocket mode** (no public IP required, good for dev):
- Launched as a background asyncio task during FastAPI lifespan
- Uses Feishu's long-connection SDK (`lark_oapi`) or native websockets
- Reconnects automatically on disconnect

**Webhook mode** (requires public IP):
- Registers `POST /channels/feishu/webhook` via FastAPI router
- Validates request signature (HMAC-SHA256 with `encrypt_key`)
- Returns `challenge` response for Feishu URL verification

### Config

```yaml
platforms:
  - name: feishu
    transport: websocket       # or "webhook"
    app_id: $FEISHU_APP_ID
    app_secret: $FEISHU_APP_SECRET
    # webhook-only:
    # verification_token: $FEISHU_VERIFICATION_TOKEN
    # encrypt_key: $FEISHU_ENCRYPT_KEY
```

### Supported Commands

| Command | Behavior |
|---------|----------|
| `/new`  | Create a new Choreo thread for this chat, replacing the old mapping |
| `/reset`| Alias for `/new` |

### Message Gating

- **DM**: all messages processed
- **Group chat**: only messages that @mention the bot are processed

## FastAPI Integration

**`gateway/app.py` lifespan**:

```python
# Startup
channel_manager = ChannelManager(db=async_session_factory)
app.state.channel_manager = channel_manager

# Load platforms from config.yaml and start adapters
adapters = platform_registry.load_from_config(settings.platforms or [])
for adapter in adapters:
    await channel_manager.register(adapter)
await channel_manager.start_all()

yield

# Shutdown
await channel_manager.stop_all()
```

**`channel/router.py`** registers webhook endpoints:

```python
router = APIRouter(prefix="/channels")

@router.post("/{platform}/webhook")
async def platform_webhook(platform: str, request: Request):
    adapter = channel_manager.get_adapter(platform)
    await adapter.handle_webhook(request)
    return {"ok": True}
```

## Extending with New Platforms

Adding Slack requires only:
1. Create `platforms/slack.py` implementing `BaseChatAdapter`
2. Call `platform_registry.register(...)` at the bottom of the file
3. Import the module in `platforms/__init__.py`
4. Add config block to `config.yaml`

No changes to `ChannelManager`, `router.py`, or `app.py`.

## Error Handling

- Adapter `connect()` failure is logged; other adapters continue running
- `send()` failure is logged; does not crash the agent run
- Webhook signature mismatch returns HTTP 403
- Missing `FEISHU_APP_ID` / `FEISHU_APP_SECRET`: adapter skipped with a clear log warning

## Out of Scope

- Media attachments (images, voice) — text only for first implementation
- HITL approval via platform buttons — deferred
- Per-user auth/permission checking — deferred
- Multiple simultaneous Feishu apps — single app only for now
