from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

from choreo.knowledge_sources.base import BaseSourceAdapter

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MAX_DOC_CHARS = 30_000


class FeishuWikiAdapter(BaseSourceAdapter):
    """从飞书知识库拉取文档，转换为 Markdown 写入 raw/。

    config 字段：
      space_id   : 知识空间 ID（必填）
      app_id     : 飞书应用 App ID（选填，默认读 settings.FEISHU_APP_ID）
      app_secret : 飞书应用 App Secret（选填，默认读 settings.FEISHU_APP_SECRET）
      page_limit : 最多拉取文档数（默认 50）
      schedule   : cron 表达式（由 puller 读取，此处不使用）
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self._space_id: str = config["space_id"]
        self._page_limit: int = int(config.get("page_limit", 50))

        from choreo.config import settings
        app_id = config.get("app_id") or settings.FEISHU_APP_ID
        app_secret = config.get("app_secret") or settings.FEISHU_APP_SECRET

        if not app_id or not app_secret:
            raise ValueError(
                "FeishuWikiAdapter 需要 app_id / app_secret（通过 config 或 settings.FEISHU_APP_ID/SECRET）"
            )

        import lark_oapi as lark
        self._client = (
            lark.Client.builder()
            .app_id(app_id)
            .app_secret(app_secret)
            .build()
        )

    async def pull(self) -> list[tuple[str, str]]:
        nodes = await asyncio.to_thread(self._list_all_nodes)
        logger.info("[%s] 共发现 %d 个节点", self.name, len(nodes))

        results: list[tuple[str, str]] = []
        for node in nodes[: self._page_limit]:
            if getattr(node, "node_type", None) not in ("doc", None, ""):
                continue
            obj_token = getattr(node, "obj_token", None)
            title = getattr(node, "title", None) or obj_token
            if not obj_token:
                continue

            content = await asyncio.to_thread(self._get_content, obj_token)
            if not content.strip():
                continue

            if len(content) > _MAX_DOC_CHARS:
                content = content[:_MAX_DOC_CHARS] + f"\n\n...（已截断，原始 {len(content)} 字符）"

            safe_title = re.sub(r"[^\w一-鿿\-]", "-", title)[:80]
            filename = f"feishu-wiki-{safe_title}.md"
            markdown = f"# {title}\n\n{content}"
            results.append((filename, markdown))
            logger.debug("[%s] 已拉取：%s (%s)", self.name, title, obj_token)

        logger.info("[%s] 完成，共写入 %d 篇文档", self.name, len(results))
        return results

    def _list_all_nodes(self) -> list:
        """BFS 遍历知识空间所有节点（含子节点）。"""
        from lark_oapi.api.wiki.v2 import ListSpaceNodeRequest

        all_nodes: list = []
        queue: list[str | None] = [None]  # None 表示根节点（无 parent_node_token）

        while queue and len(all_nodes) < self._page_limit * 2:
            parent_token = queue.pop(0)
            page_token: str | None = None

            while True:
                builder = (
                    ListSpaceNodeRequest.builder()
                    .space_id(self._space_id)
                    .page_size(50)
                )
                if parent_token:
                    builder = builder.parent_node_token(parent_token)
                if page_token:
                    builder = builder.page_token(page_token)

                resp = self._client.wiki.v2.space_node.list(builder.build())
                if not resp.success():
                    logger.warning(
                        "[%s] 节点列表失败（parent=%s）: code=%s msg=%s",
                        self.name, parent_token, resp.code, resp.msg,
                    )
                    break

                for item in resp.data.items or []:
                    all_nodes.append(item)
                    if getattr(item, "has_child", False):
                        queue.append(getattr(item, "node_token", None))

                if resp.data.has_more and resp.data.page_token:
                    page_token = resp.data.page_token
                else:
                    break

        return all_nodes

    def _get_content(self, doc_token: str) -> str:
        """通过 docx API 获取文档纯文本内容。"""
        from lark_oapi.api.docx.v1 import RawContentDocumentRequest

        req = RawContentDocumentRequest.builder().document_id(doc_token).build()
        resp = self._client.docx.v1.document.raw_content(req)
        if not resp.success():
            logger.warning(
                "[%s] 内容获取失败（doc=%s）: code=%s msg=%s",
                self.name, doc_token, resp.code, resp.msg,
            )
            return ""
        return getattr(resp.data, "content", "") or ""
