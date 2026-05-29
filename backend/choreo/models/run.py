from pydantic import BaseModel


class RunInput(BaseModel):
    input: dict | None = None   # None 表示从 interrupt 恢复
    config: dict = {}
    context: dict = {}          # 自定义参数，透传到 config["configurable"]


class StateUpdate(BaseModel):
    values: dict  # {"decisions": [{"type": "approve"}]} 等
