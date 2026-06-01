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
    ))
    assert reg.create_adapter("missing", {}) is None


def test_registry_unknown_platform_returns_none():
    reg = PlatformRegistry()
    assert reg.create_adapter("nope", {}) is None


def test_registry_load_from_config():
    reg = PlatformRegistry()
    reg.register(PlatformEntry(
        name="fake",
        label="Fake",
        adapter_factory=lambda cfg: _FakeAdapter(cfg),
        check_fn=lambda: True,
    ))
    adapters = reg.load_from_config([{"name": "fake"}, {"name": "unknown"}])
    assert len(adapters) == 1
    assert isinstance(adapters[0], _FakeAdapter)
