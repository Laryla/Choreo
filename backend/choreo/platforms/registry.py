from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class PlatformEntry:
    name: str
    label: str
    adapter_factory: Callable[[dict], Any]
    check_fn: Callable[[], bool]
    required_env: list[str] = field(default_factory=list)
    install_hint: str = ""


class PlatformRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, PlatformEntry] = {}

    def register(self, entry: PlatformEntry) -> None:
        self._entries[entry.name] = entry
        logger.debug("Registered platform adapter: %s", entry.name)

    def get(self, name: str) -> Optional[PlatformEntry]:
        return self._entries.get(name)

    def all_names(self) -> list[str]:
        return list(self._entries.keys())

    def create_adapter(self, name: str, config: dict) -> Optional[Any]:
        entry = self._entries.get(name)
        if entry is None:
            return None
        if not entry.check_fn():
            hint = f" ({entry.install_hint})" if entry.install_hint else ""
            logger.warning("Platform '%s' requirements not met%s", entry.label, hint)
            return None
        try:
            return entry.adapter_factory(config)
        except Exception:
            logger.exception("Failed to create adapter for platform '%s'", entry.label)
            return None

    def load_from_config(self, platforms_config: list[dict]) -> list[Any]:
        adapters = []
        for cfg in platforms_config:
            name = cfg.get("name", "")
            adapter = self.create_adapter(name, cfg)
            if adapter is not None:
                adapters.append(adapter)
        return adapters


# Module-level singleton — adapters self-register at import time
platform_registry = PlatformRegistry()
