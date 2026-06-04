from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class BaseCollector(ABC):
    """收集指定时间之后的用户行为信号。"""

    @abstractmethod
    async def collect(self, since: datetime) -> str:
        """返回 `since` 之后的行为摘要（Markdown 格式字符串）。

        如无数据或采集器不可用，返回空字符串。
        不抛出异常——调用方期望优雅降级。
        """
        ...
