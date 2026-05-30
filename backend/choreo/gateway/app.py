import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import yaml as _yaml
from choreo.db import init_db
from choreo.config import settings
from choreo.agents import create_choreo_agent, set_agent
from choreo.sandbox import get_sandbox_manager, set_sandbox_manager, SandboxManager
from choreo.skills import set_skill_store, LocalSkillStore
from choreo.skills.bundled import sync_builtin_skills
from choreo.gateway.routers import threads, runs, tasks, history, models
from choreo.gateway.routers import skills as skills_router
from choreo.gateway.routers import mcp as mcp_router
from choreo.mcp import McpManager, set_mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. 初始化 SkillStore 并同步内置技能
    _cfg_path = Path(__file__).parent.parent.parent / "config.yaml"
    with open(_cfg_path, encoding="utf-8") as _f:
        _cfg = _yaml.safe_load(_f) or {}
    _skills_root = Path(__file__).parent.parent.parent / _cfg.get("skills_dir", "./skills")
    _skill_store = LocalSkillStore(_skills_root)
    await sync_builtin_skills(_skill_store)
    set_skill_store(_skill_store)

    # 初始化 McpManager（连接失败不阻塞启动）
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()

    # 1. 建表（幂等）
    await init_db()

    # 2. 初始化 SandboxManager
    manager = SandboxManager()
    set_sandbox_manager(manager)
    eviction_task = asyncio.create_task(manager.evict_idle())

    # 3. 初始化 PostgreSQL checkpointer，持久化 LangGraph 对话状态
    async with AsyncPostgresSaver.from_conn_string(
        settings.DATABASE_URL_PSYCOPG
    ) as checkpointer:
        await checkpointer.setup()       # 自动建 checkpoint_* 表
        set_agent(create_choreo_agent(checkpointer))
        yield

    # 清理
    eviction_task.cancel()
    try:
        await eviction_task
    except asyncio.CancelledError:
        pass
    await manager.shutdown_all()


app = FastAPI(title="Choreo API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads.router, prefix="/threads",     tags=["threads"])
app.include_router(runs.router,    prefix="/threads",     tags=["runs"])
app.include_router(tasks.router,   prefix="/api/tasks",   tags=["tasks"])
app.include_router(history.router, prefix="/api/history", tags=["history"])
app.include_router(models.router,  prefix="/models",      tags=["models"])
app.include_router(skills_router.router, prefix="/api/skills", tags=["skills"])
app.include_router(mcp_router.router,    prefix="/api/mcp",    tags=["mcp"])
