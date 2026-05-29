"""
Sandbox module - Provides isolated execution environments for code.

Includes base abstract class, concrete provider implementations,
and a global SandboxManager singleton for per-thread lifecycle management.
"""

from choreo.sandbox.base import BaseSandbox
from choreo.sandbox.manager import SandboxManager

_manager: SandboxManager | None = None


def get_sandbox_manager() -> SandboxManager:
    """Return the process-wide SandboxManager singleton, creating it if needed."""
    global _manager
    if _manager is None:
        _manager = SandboxManager()
    return _manager


def set_sandbox_manager(manager: SandboxManager) -> None:
    """Replace the global SandboxManager (useful for testing or custom config)."""
    global _manager
    _manager = manager


__all__ = ["BaseSandbox", "SandboxManager", "get_sandbox_manager", "set_sandbox_manager"]
