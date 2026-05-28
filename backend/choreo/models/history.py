from pydantic import BaseModel


class HistoryRecord(BaseModel):
    id: str
    task_id: str | None = None
    started_at: int
    finished_at: int | None = None
    status: str = "running"  # running | success | error
    output_path: str | None = None
