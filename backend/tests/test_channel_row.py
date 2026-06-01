import pytest
from choreo.db import ChannelRow, Base
from sqlalchemy import UniqueConstraint


def test_channel_row_has_required_columns():
    cols = {c.key: c for c in ChannelRow.__table__.columns}
    assert "platform" in cols
    assert "chat_id" in cols
    assert "thread_id" in cols
    assert "user_id" in cols
    assert "created_at" in cols
    assert "updated_at" in cols


def test_channel_row_nullable_fields():
    cols = {c.key: c for c in ChannelRow.__table__.columns}
    assert cols["user_id"].nullable is True
    assert cols["platform"].nullable is False
    assert cols["chat_id"].nullable is False
    assert cols["thread_id"].nullable is False


def test_channel_row_unique_constraint():
    constraints = {
        c.name
        for c in ChannelRow.__table__.constraints
        if isinstance(c, UniqueConstraint)
    }
    assert "uq_channel_platform_chat" in constraints
