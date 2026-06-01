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
    with patch.object(manager, "_create_thread", new_callable=AsyncMock, return_value="tid_new") as mock_create, \
         patch.object(manager, "_save_channel", new_callable=AsyncMock) as mock_save:
        await manager.handle(event)
        mock_create.assert_called_once()
        mock_save.assert_called_once_with("feishu", "chat_001", "tid_new", "user_1")
    assert len(adapter.sent) == 1
    assert "新对话" in adapter.sent[0][1]


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


@pytest.mark.asyncio
async def test_handle_empty_agent_reply_sends_nothing(manager, adapter):
    event = MessageEvent(platform="feishu", chat_id="chat_001", user_id="user_1", text="hello")
    with patch.object(manager, "_get_or_create_thread_id", new_callable=AsyncMock, return_value="tid_123"), \
         patch.object(manager, "_call_agent", new_callable=AsyncMock, return_value=""):
        await manager.handle(event)
    assert adapter.sent == []


@pytest.mark.asyncio
async def test_notify_unknown_platform_is_noop(manager):
    # Should not raise
    await manager.notify("slack", "chat_001", "hello")
