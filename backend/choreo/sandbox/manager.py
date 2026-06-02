"""
SandboxManager — per-thread sandbox lifecycle manager.

Responsibilities:
- Create sandboxes on demand (one per thread_id) via sandbox_factory.
- Prevent duplicate creation under concurrent requests using per-thread locks.
- Evict idle sandboxes automatically based on idle_timeout from config.yaml.
"""

import asyncio
import logging
import time

from choreo.sandbox.base import BaseSandbox
from choreo.sandbox.factory import get_active_sandbox_config, sandbox_factory

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    Manages a pool of BaseSandbox instances keyed by thread_id.

    Usage::

        manager = SandboxManager()
        sandbox = await manager.acquire(thread_id="t-123")
        # ... use sandbox ...
        await manager.release(thread_id="t-123")   # mark as idle (keeps alive)
        await manager.destroy(thread_id="t-123")   # explicit teardown
    """

    def __init__(self) -> None:
        self._registry: dict[str, BaseSandbox] = {}
        self._last_used: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

        try:
            config = get_active_sandbox_config()
            self._idle_timeout: int = int(config.get("idle_timeout", 1800))
        except Exception:
            self._idle_timeout = 1800

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def acquire(
        self, thread_id: str, sandbox_name: str | None = None
    ) -> BaseSandbox:
        """
        Return the sandbox for *thread_id*, creating and starting it if needed.

        A per-thread asyncio.Lock prevents concurrent double-creation for the
        same thread_id.

        Args:
            thread_id:    Unique identifier for the conversation/agent thread.
            sandbox_name: Override the active sandbox name from config.yaml.

        Returns:
            A running BaseSandbox instance.
        """
        lock = self._locks.setdefault(thread_id, asyncio.Lock())

        async with lock:
            if thread_id in self._registry:
                self._last_used[thread_id] = time.time()
                return self._registry[thread_id]

            extra: dict = {}
            try:
                from choreo.skills import get_skill_store
                extra["skills_dir"] = str(get_skill_store()._root.resolve())
            except Exception:
                pass
            try:
                from choreo.sandbox.factory import _load_yaml
                from pathlib import Path
                _cfg = _load_yaml(None)
                _raw = _cfg.get("output_dir")
                if _raw:
                    # Per-thread output subdir so each thread's files are isolated
                    _base = Path(_raw).expanduser().resolve()
                    _thread_output = _base / thread_id
                    _thread_output.mkdir(parents=True, exist_ok=True)
                    extra["output_dir"] = str(_thread_output)
            except Exception:
                pass
            # Per-thread container name for aios provider
            extra["container_name"] = f"choreo-aios-{thread_id[:16]}"
            sandbox = sandbox_factory(sandbox_name, extra_kwargs=extra)
            await sandbox.start()

            self._registry[thread_id] = sandbox
            self._last_used[thread_id] = time.time()

            logger.info(
                "sandbox acquired: thread=%s provider=%s",
                thread_id,
                type(sandbox).__name__,
            )

        return sandbox

    def get(self, thread_id: str) -> BaseSandbox | None:
        """
        Return the existing sandbox for *thread_id*, or None if not present.

        Does not create a new sandbox — callers must use :meth:`acquire` when
        they need to guarantee a running instance.
        """
        return self._registry.get(thread_id)

    async def release(self, thread_id: str) -> None:
        """
        Mark the sandbox as recently used (reset idle timer) without destroying it.

        Call this after a tool/agent interaction completes successfully so the
        sandbox is not evicted prematurely.
        """
        self._last_used[thread_id] = time.time()

    async def destroy(self, thread_id: str) -> None:
        """
        Stop and destroy the sandbox associated with *thread_id*.

        Silently ignores unknown thread_ids. Logs a warning (does not raise)
        if destruction fails.
        """
        sandbox = self._registry.pop(thread_id, None)
        if sandbox is None:
            return

        try:
            await sandbox.destroy()
        except Exception as exc:
            logger.warning(
                "sandbox destroy failed: thread=%s error=%r",
                thread_id,
                exc,
            )
        finally:
            self._last_used.pop(thread_id, None)
            self._locks.pop(thread_id, None)

    async def shutdown_all(self) -> None:
        """Destroy all managed sandboxes (e.g., on application shutdown)."""
        for thread_id in list(self._registry.keys()):
            await self.destroy(thread_id)

    async def evict_idle(self) -> None:
        """
        Background task: periodically destroy sandboxes that have been idle
        longer than *idle_timeout* seconds.

        Runs forever; intended to be launched with ``asyncio.create_task``.
        Exceptions are caught and logged so the loop never silently exits.
        """
        while True:
            try:
                await asyncio.sleep(10)
                now = time.time()
                for thread_id in list(self._last_used.keys()):
                    last = self._last_used.get(thread_id)
                    if last is not None and (now - last) > self._idle_timeout:
                        logger.info(
                            "evicting idle sandbox: thread=%s idle=%.0fs",
                            thread_id,
                            now - last,
                        )
                        await self.destroy(thread_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("evict_idle encountered an error: %r", exc)
                continue
