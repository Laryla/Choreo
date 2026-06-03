from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from choreo.db import TaskRow, TaskRunRow


class BaseNotifier(ABC):
    @abstractmethod
    async def send(self, task: "TaskRow", run: "TaskRunRow") -> None: ...
