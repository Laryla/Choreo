import json
import pytest
from choreo.platforms.feishu import FeishuAdapter


@pytest.mark.asyncio
async def test_webhook_url_verification():
    """Feishu URL verification challenge must be echoed back."""
    adapter = FeishuAdapter({"transport": "webhook"})
    result = await adapter.handle_webhook({
        "type": "url_verification",
        "challenge": "test_challenge_abc",
    })
    assert result == {"challenge": "test_challenge_abc"}


@pytest.mark.asyncio
async def test_webhook_text_message_dispatched():
    """Text message from DM triggers message handler with correct fields."""
    adapter = FeishuAdapter({"transport": "webhook"})
    received = []

    async def handler(event):
        received.append(event)

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
                "content": json.dumps({"text": "hello feishu"}),
                "message_id": "om_msg1",
                "mentions": [],
            },
        },
    }
    await adapter.handle_webhook(payload)
    assert len(received) == 1
    assert received[0].text == "hello feishu"
    assert received[0].chat_id == "oc_chat1"
    assert received[0].user_id == "ou_user1"
    assert received[0].platform == "feishu"


@pytest.mark.asyncio
async def test_webhook_non_text_message_ignored():
    """Non-text messages (image, file, etc.) are ignored."""
    adapter = FeishuAdapter({"transport": "webhook"})
    received = []
    adapter.set_message_handler(lambda e: received.append(e))

    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user1"}},
            "message": {
                "chat_id": "oc_chat1",
                "chat_type": "p2p",
                "message_type": "image",
                "content": "{}",
                "mentions": [],
            },
        },
    }
    await adapter.handle_webhook(payload)
    assert received == []


@pytest.mark.asyncio
async def test_webhook_group_message_without_mention_ignored():
    """Group messages without @mention are ignored when bot_open_id is set."""
    import os
    os.environ["FEISHU_BOT_OPEN_ID"] = "ou_bot123"
    # Re-import settings after env change
    from choreo.config import settings
    settings.__class__.model_config  # access to ensure reload doesn't crash

    adapter = FeishuAdapter({"transport": "webhook"})
    # Simulate bot_open_id being set
    adapter._bot_open_id = "ou_bot123"
    received = []
    adapter.set_message_handler(lambda e: received.append(e))

    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user1"}},
            "message": {
                "chat_id": "oc_group1",
                "chat_type": "group",
                "message_type": "text",
                "content": json.dumps({"text": "hello everyone"}),
                "mentions": [],  # No mention
            },
        },
    }
    await adapter.handle_webhook(payload)
    assert received == []


def test_feishu_adapter_self_registers():
    """FeishuAdapter must register itself in platform_registry on import."""
    from choreo.platforms.registry import platform_registry
    entry = platform_registry.get("feishu")
    assert entry is not None
    assert entry.name == "feishu"
