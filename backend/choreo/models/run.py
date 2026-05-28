from pydantic import BaseModel


class RunInput(BaseModel):
    input: dict | None = None   # None 表示从 interrupt 恢复
    config: dict = {}


class StateUpdate(BaseModel):
    values: dict  # {"decisions": [{"type": "approve"}]} 等
