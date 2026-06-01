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
