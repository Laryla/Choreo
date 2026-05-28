from pydantic import BaseModel, Field
from typing import Literal
import uuid
import time


class TaskCreate(BaseModel):
    description: str
    cron: str
    script_path: str


class TaskPatch(BaseModel):
    status: Literal["active", "paused"] | None = None


class Task(TaskCreate):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: Literal["active", "paused"] = "active"
    last_run: int | None = None
    next_run: int | None = None
