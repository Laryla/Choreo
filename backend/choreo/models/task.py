from pydantic import BaseModel, Field
from typing import Literal
import uuid
import time


class TaskCreate(BaseModel):
    description: str
    cron: str
    prompt: str
    script_path: str = ""
    notify_config: dict = Field(default_factory=dict)


class TaskPatch(BaseModel):
    status: Literal["active", "paused"] | None = None


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    cron: str
    prompt: str
    script_path: str = ""
    notify_config: dict = Field(default_factory=dict)
    status: Literal["active", "paused"] = "active"
    last_run: int | None = None
    next_run: int | None = None


class TaskRunCreate(BaseModel):
    task_id: str
    status: str = "pending"
    started_at: int = Field(default_factory=lambda: int(time.time() * 1000))


class TaskRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    status: str  # pending|running|success|failed
    started_at: int
    finished_at: int | None = None
    output: str = ""
    error: str | None = None
