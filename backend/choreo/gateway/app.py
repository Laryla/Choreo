from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from choreo.gateway.routers import threads, runs, tasks, history
from choreo.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


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
