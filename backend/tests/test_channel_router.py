import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from choreo.channel.router import make_channel_router
from choreo.channel.manager import ChannelManager
from choreo.platforms.base import BaseChatAdapter, SendResult


class FakeAdapter(BaseChatAdapter):
    def __init__(self):
        super().__init__({})
        self.webhook_calls: list[dict] = []

    async def connect(self): pass
    async def disconnect(self): pass
    async def send(self, chat_id, text): return SendResult(success=True)
    async def handle_webhook(self, payload: dict):
        self.webhook_calls.append(payload)
        return None


@pytest.fixture
def app_with_manager():
    test_app = FastAPI()
    manager = ChannelManager()
    test_app.state.channel_manager = manager
    test_app.include_router(make_channel_router())
    return test_app, manager


def test_webhook_unknown_platform_returns_404(app_with_manager):
    test_app, _ = app_with_manager
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.post("/channels/unknown/webhook", json={})
    assert resp.status_code == 404


def test_webhook_no_channel_manager_returns_503():
    test_app = FastAPI()
    test_app.include_router(make_channel_router())
    # No channel_manager set on app.state
    client = TestClient(test_app, raise_server_exceptions=False)
    resp = client.post("/channels/feishu/webhook", json={})
    assert resp.status_code == 503


def test_webhook_known_platform_calls_adapter(app_with_manager):
    test_app, manager = app_with_manager
    adapter = FakeAdapter()
    manager.register_adapter("feishu", adapter)
    client = TestClient(test_app)
    payload = {"type": "url_verification", "challenge": "abc123"}
    resp = client.post("/channels/feishu/webhook", json=payload)
    assert resp.status_code == 200
    assert adapter.webhook_calls == [payload]


def test_webhook_adapter_result_returned(app_with_manager):
    """When handle_webhook returns a dict, it becomes the HTTP response."""
    test_app, manager = app_with_manager

    class ChallengeAdapter(BaseChatAdapter):
        async def connect(self): pass
        async def disconnect(self): pass
        async def send(self, chat_id, text): return SendResult(success=True)
        async def handle_webhook(self, payload: dict):
            return {"challenge": payload.get("challenge")}

    manager.register_adapter("feishu", ChallengeAdapter({}))
    client = TestClient(test_app)
    resp = client.post("/channels/feishu/webhook", json={"challenge": "xyz"})
    assert resp.status_code == 200
    assert resp.json() == {"challenge": "xyz"}
