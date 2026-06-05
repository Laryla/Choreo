from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import BigInteger, Boolean, Integer, String, Text, JSON, UniqueConstraint
from choreo.config import settings
import uuid as _uuid
import time

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(String)
    cron: Mapped[str] = mapped_column(String)
    script_path: Mapped[str] = mapped_column(String, default="")
    prompt: Mapped[str] = mapped_column(String, default="")
    notify_config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="active")
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class TaskRunRow(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|success|failed
    started_at: Mapped[int] = mapped_column(BigInteger, default=0)
    finished_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    output: Mapped[str] = mapped_column(String, default="")
    error: Mapped[str | None] = mapped_column(String, nullable=True)


class ThreadRow(Base):
    __tablename__ = "threads"

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="idle")
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=0)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class McpServerRow(Base):
    __tablename__ = "mcp_servers"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    transport: Mapped[str] = mapped_column(String, default="stdio")   # stdio | sse | http
    command: Mapped[str | None] = mapped_column(String, nullable=True)
    args: Mapped[list] = mapped_column(JSON, default=list)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    env: Mapped[dict] = mapped_column(JSON, default=dict)
    tools_config: Mapped[dict] = mapped_column(JSON, default=dict)    # {tool_name: {approval, enabled}}
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=0)


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(_uuid.uuid4()))
    provider: Mapped[str] = mapped_column(String, nullable=False)       # "github" | "feishu"
    provider_id: Mapped[str] = mapped_column(String, nullable=False)    # provider 内部 uid
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time()))

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_user_provider"),
    )


class ChannelRow(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    chat_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time()))
    updated_at: Mapped[int] = mapped_column(
        BigInteger,
        default=lambda: int(time.time()),
        onupdate=lambda: int(time.time()),
    )

    __table_args__ = (
        UniqueConstraint("platform", "chat_id", name="uq_channel_platform_chat"),
    )


class SkillSuggestionRow(Base):
    __tablename__ = "skill_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String, index=True)
    category: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[int] = mapped_column(BigInteger, default=lambda: int(time.time()))


async def init_db():
    """启动时自动创建所有表（幂等，表已存在不会报错）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
