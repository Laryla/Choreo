import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from choreo.config import settings
from choreo.db import init_db
from choreo.agents import create_choreo_agent, set_agent
from choreo.agents.registry import set_scheduler
from choreo.scheduler import TaskScheduler
from choreo.sandbox import get_sandbox_manager, set_sandbox_manager, SandboxManager
from choreo.skills import set_skill_store, LocalSkillStore
from choreo.skills.bundled import sync_builtin_skills
from choreo.skills.curator import SkillCurator
from choreo.gateway.routers import threads, runs, tasks, history, models
from choreo.gateway.routers import skills as skills_router
from choreo.gateway.routers import mcp as mcp_router
from choreo.gateway.routers import output as output_router
from choreo.mcp import McpManager, set_mcp_manager
from choreo.gateway.routers import auth as auth_router
from choreo.gateway.routers import knowledge as knowledge_router
from choreo.auth.deps import require_auth
from choreo.kb.init import kb_init
from choreo.channel import ChannelManager, make_channel_router
from choreo.platforms.registry import platform_registry


def _setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. 初始化 SkillStore 并同步内置技能
    _skills_root = Path(__file__).parents[2] / settings.SKILLS_DIR
    _skill_store = LocalSkillStore(_skills_root)
    await sync_builtin_skills(_skill_store)
    set_skill_store(_skill_store)

    # 0b. 启动技能库馆长（后台定期整合）
    _curator = SkillCurator(settings.CURATOR)
    _curator.start()

    # 1. 建表（幂等）
    await init_db()
    kb_init(settings.KNOWLEDGE_BASE_DIR)

    # 1b. 启动任务调度器
    task_scheduler = TaskScheduler()
    await task_scheduler.start()
    app.state.task_scheduler = task_scheduler
    set_scheduler(task_scheduler)

    # 2. 初始化 McpManager（连接失败不阻塞启动）
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()

    # 3. 初始化 SandboxManager
    manager = SandboxManager()
    set_sandbox_manager(manager)
    eviction_task = asyncio.create_task(manager.evict_idle())

    # 4. 外部知识来源拉取调度器
    from choreo.knowledge_sources.puller import start_pull_scheduler
    pull_scheduler = start_pull_scheduler(settings.KNOWLEDGE_SOURCES)
    app.state.pull_scheduler = pull_scheduler

    # 5. 用户画像调度器
    from choreo.activity.profiler import start_profile_scheduler
    profile_scheduler = start_profile_scheduler(settings.ACTIVITY_PROFILE)
    app.state.profile_scheduler = profile_scheduler

    # 6. 初始化 PostgreSQL checkpointer，持久化 LangGraph 对话状态
    async with AsyncPostgresSaver.from_conn_string(
        settings.DATABASE_URL_PSYCOPG
    ) as checkpointer:
        await checkpointer.setup()
        set_agent(create_choreo_agent(checkpointer))

        # 7. 初始化 ChannelManager，连接聊天平台
        _channel_manager = ChannelManager()
        app.state.channel_manager = _channel_manager
        if settings.FEISHU_ENABLED:
            import choreo.platforms.feishu  # noqa: F401 — triggers self-registration
        if settings.PLATFORMS and settings.FEISHU_ENABLED:
            _adapters = platform_registry.load_from_config(settings.PLATFORMS)
            for _adapter in _adapters:
                _platform_name = _adapter._config.get("name", "unknown")
                _channel_manager.register_adapter(_platform_name, _adapter)
            await _channel_manager.start_all()

        try:
            yield
        finally:
            await _channel_manager.stop_all()
            task_scheduler.shutdown()
            if pull_scheduler is not None:
                pull_scheduler.shutdown(wait=False)
            if profile_scheduler is not None:
                profile_scheduler.shutdown(wait=False)

    # 清理
    _curator.stop()
    eviction_task.cancel()
    try:
        await eviction_task
    except asyncio.CancelledError:
        pass
    await manager.shutdown_all()


app = FastAPI(title="Choreo API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router.router, prefix="/auth", tags=["auth"])

app.include_router(threads.router, prefix="/threads",     tags=["threads"],  dependencies=[Depends(require_auth)])
app.include_router(runs.router,    prefix="/threads",     tags=["runs"],     dependencies=[Depends(require_auth)])
app.include_router(tasks.router,   prefix="/api/tasks",   tags=["tasks"],    dependencies=[Depends(require_auth)])
app.include_router(history.router, prefix="/api/history", tags=["history"],  dependencies=[Depends(require_auth)])
app.include_router(models.router,  prefix="/models",      tags=["models"],   dependencies=[Depends(require_auth)])
app.include_router(skills_router.router, prefix="/api/skills", tags=["skills"], dependencies=[Depends(require_auth)])
app.include_router(mcp_router.router,    prefix="/api/mcp",    tags=["mcp"],    dependencies=[Depends(require_auth)])
app.include_router(output_router.router, prefix="/api",        tags=["output"])

app.include_router(knowledge_router.router, prefix="/api/kb", tags=["knowledge"], dependencies=[Depends(require_auth)])

# Channel webhook endpoints (no auth — Feishu validates via its own mechanism)
app.include_router(make_channel_router())
