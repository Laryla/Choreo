from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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
    def create_adapter(self, name: str, config: dict) -> Optional[Any]:
        return None
    def load_from_config(self, platforms_config: list[dict]) -> list[Any]:
        return []

platform_registry = PlatformRegistry()
