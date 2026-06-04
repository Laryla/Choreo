from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSourceAdapter(ABC):
    """从外部知识来源拉取文档写入 KB raw/。"""

    def __init__(self, config: dict) -> None:
        self.config = config
        self.name: str = config.get("name", type(self).__name__)

    @abstractmethod
    async def pull(self) -> list[tuple[str, str]]:
        """返回 (filename, markdown_content) 列表，写入 raw/。

        filename: 相对文件名，如 "feishu-wiki-my-page.md"
        markdown_content: 完整 Markdown 文本
        """
        ...
