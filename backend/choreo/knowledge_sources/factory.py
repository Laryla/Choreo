from __future__ import annotations

import importlib
import logging

from choreo.knowledge_sources.base import BaseSourceAdapter

logger = logging.getLogger(__name__)

_ADAPTERS: dict[str, str] = {
    "feishu_wiki": "choreo.knowledge_sources.feishu_wiki:FeishuWikiAdapter",
    "github": "choreo.knowledge_sources.github_source:GitHubSourceAdapter",
    # "yuque": "choreo.knowledge_sources.yuque:YuqueAdapter",
    # "notion": "choreo.knowledge_sources.notion:NotionAdapter",
}


def _load_class(dotted: str):
    module_path, class_name = dotted.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def load_sources(configs: list[dict]) -> list[BaseSourceAdapter]:
    """从 config.yaml knowledge_sources 列表实例化适配器。"""
    adapters: list[BaseSourceAdapter] = []
    for cfg in configs:
        type_key = cfg.get("type", "")
        dotted = _ADAPTERS.get(type_key)
        if not dotted:
            logger.warning("未知 knowledge_sources type: %r，跳过", type_key)
            continue
        try:
            cls = _load_class(dotted)
            adapters.append(cls(cfg))
            logger.info("已加载知识来源适配器: %s (%s)", cfg.get("name", type_key), type_key)
        except Exception as exc:
            logger.error("加载适配器 %r 失败: %r", type_key, exc)
    return adapters
