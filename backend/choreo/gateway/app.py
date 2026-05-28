from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from choreo.db import init_db
from choreo.config import settings
from choreo.agents import create_choreo_agent, set_agent
from choreo.gateway.routers import threads, runs, tasks, history


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 建表（幂等）
    await init_db()

    # 2. 初始化 PostgreSQL checkpointer，持久化 LangGraph 对话状态
    async with AsyncPostgresSaver.from_conn_string(
        settings.DATABASE_URL_PSYCOPG
    ) as checkpointer:
        await checkpointer.setup()       # 自动建 checkpoint_* 表
        set_agent(create_choreo_agent(checkpointer))
        yield
    # lifespan 退出时连接池自动关闭


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
