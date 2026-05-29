from pydantic import BaseModel, Field

import time
import uuid


class Thread(BaseModel):
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = Field(default_factory=lambda: int(time.time()))


class ThreadState(BaseModel):
    thread_id: str
    status: str = "idle"  # idle | running | interrupted
    title: str | None = None
