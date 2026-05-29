"""
pytest fixtures 共用配置。

运行前确保 .env 已设置：
  LANGSMITH_API_KEY=lsv2_...
  LANGSMITH_TRACING=true
  LANGSMITH_PROJECT=choreo-dev
"""
import os
import asyncio
import uuid
import pytest
from langgraph.checkpoint.memory import InMemorySaver

# 强制开启 LangSmith tracing（pytest 运行时生效）
os.environ.setdefault("LANGSMITH_TRACING", "true")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def agent():
    """共享一个带内存 checkpointer 的 agent 实例（不依赖 PostgreSQL）。"""
    from choreo.agents.choreo_agent import create_choreo_agent
    return create_choreo_agent(InMemorySaver())


@pytest.fixture
def thread_id():
    """每个测试用独立 thread，避免状态污染。"""
    return str(uuid.uuid4())


@pytest.fixture(scope="session")
def sandbox(tmp_path_factory):
    """LocalSandbox，指向临时目录，测试结束后自动清理。"""
    import asyncio
    from choreo.sandbox.providers.local import LocalSandbox
    workdir = str(tmp_path_factory.mktemp("sandbox"))
    sb = LocalSandbox(workspace_dir=workdir, timeout=30)
    asyncio.get_event_loop().run_until_complete(sb.start())
    yield sb
    # 不 destroy（LocalSandbox.destroy 只清标记，不删目录）
