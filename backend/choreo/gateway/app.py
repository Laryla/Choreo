import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
import yaml as _yaml
from choreo.db import init_db
from choreo.config import settings
from choreo.agents import create_choreo_agent, set_agent
from choreo.sandbox import get_sandbox_manager, set_sandbox_manager, SandboxManager
from choreo.skills import set_skill_store, LocalSkillStore
from choreo.skills.bundled import sync_builtin_skills
from choreo.skills.curator import SkillCurator
from choreo.gateway.routers import threads, runs, tasks, history, models
from choreo.gateway.routers import skills as skills_router
from choreo.gateway.routers import mcp as mcp_router
from choreo.mcp import McpManager, set_mcp_manager
from choreo.gateway.routers import auth as auth_router
from choreo.auth.deps import require_auth
from choreo.channel import ChannelManager, make_channel_router
from choreo.platforms.registry import platform_registry


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

    # 0b. 启动技能库馆长（后台定期整合）
    _curator = SkillCurator(_cfg.get("curator") or {})
    _curator.start()

    # 1. 建表（幂等）
    await init_db()

    # 2. 初始化 McpManager（连接失败不阻塞启动）
    mcp_manager = McpManager()
    set_mcp_manager(mcp_manager)
    await mcp_manager.start()

    # 4. 初始化 SandboxManager
    manager = SandboxManager()
    set_sandbox_manager(manager)
    eviction_task = asyncio.create_task(manager.evict_idle())

    # 5. 初始化 PostgreSQL checkpointer，持久化 LangGraph 对话状态
    async with AsyncPostgresSaver.from_conn_string(
        settings.DATABASE_URL_PSYCOPG
    ) as checkpointer:
        await checkpointer.setup()       # 自动建 checkpoint_* 表
        set_agent(create_choreo_agent(checkpointer))

        # 6. 初始化 ChannelManager，连接聊天平台
        _platforms_cfg = _cfg.get("platforms") or []
        _channel_manager = ChannelManager()
        app.state.channel_manager = _channel_manager
        if settings.FEISHU_ENABLED:
            import choreo.platforms.feishu  # noqa: F401 — triggers self-registration
        if _platforms_cfg and settings.FEISHU_ENABLED:
            _adapters = platform_registry.load_from_config(_platforms_cfg)
            for _adapter in _adapters:
                _platform_name = _adapter._config.get("name", "unknown")
                _channel_manager.register_adapter(_platform_name, _adapter)
            await _channel_manager.start_all()

        try:
            yield
        finally:
            await _channel_manager.stop_all()

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

# Channel webhook endpoints (no auth — Feishu validates via its own mechanism)
app.include_router(make_channel_router())
