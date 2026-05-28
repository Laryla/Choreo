# 入口：从 gateway 层导出 FastAPI app
# 启动：uvicorn choreo.api:app
from choreo.gateway.app import app

__all__ = ["app"]
