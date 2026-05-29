"""
LLMSandboxAdapter - 基于 llm-sandbox 库的沙箱适配器。

封装 SandboxSession，手动管理 context manager 生命周期，
避免 with 语句导致的作用域问题。
"""

import asyncio
import tempfile
from pathlib import Path

from choreo.sandbox.base import BaseSandbox


class LLMSandboxAdapter(BaseSandbox):
    """
    基于 llm_sandbox.SandboxSession 的沙箱适配器。

    Args:
        backend:   后端类型，默认 'docker'。
        image:     Docker 镜像，默认 'python:3.11'。
        timeout:   bash 命令的默认超时秒数，默认 60。
        cpu_count: 可选 CPU 数量限制。
        mem_limit: 可选内存限制（如 '512m'）。
    """

    def __init__(
        self,
        backend: str = "docker",
        image: str = "python:3.11",
        timeout: int = 60,
        cpu_count: int | None = None,
        mem_limit: str | None = None,
        **_kwargs,
    ) -> None:
        try:
            from llm_sandbox import SandboxSession  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "请安装 llm-sandbox: uv add llm-sandbox[docker]"
            ) from exc

        self._backend = backend
        self._image = image
        self._default_timeout = timeout
        self._cpu_count = cpu_count
        self._mem_limit = mem_limit
        self._session = None

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """手动进入 SandboxSession context manager，启动容器。"""
        from llm_sandbox import SandboxSession

        def _start() -> None:
            kwargs = {
                "lang": "python",
                "backend": self._backend,
                "image": self._image,
            }
            if self._cpu_count is not None:
                kwargs["cpu_count"] = self._cpu_count
            if self._mem_limit is not None:
                kwargs["mem_limit"] = self._mem_limit

            self._session = SandboxSession(**kwargs)
            self._session.__enter__()

        await asyncio.to_thread(_start)

    async def stop(self) -> None:
        """空操作（llm_sandbox 无暂停接口）。"""
        pass

    async def destroy(self) -> None:
        """手动退出 context manager，清理容器资源。"""
        def _destroy() -> None:
            if self._session is not None:
                try:
                    self._session.__exit__(None, None, None)
                except Exception:
                    pass
                self._session = None

        await asyncio.to_thread(_destroy)

    def is_running(self) -> bool:
        return self._session is not None

    # ── 文件操作 ──────────────────────────────────────────────────────

    async def read_file(
        self, path: str, offset: int = 0, limit: int = 2000
    ) -> str:
        """
        通过 copy_from_runtime 读取容器内文件，返回带行号前缀的字符串。

        使用文件拷贝而非 cat，避免大文件或特殊字符导致的截断问题。
        """
        self._assert_running()

        def _read() -> str:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".txt"
            ) as tmp:
                tmp_path = tmp.name

            try:
                self._session.copy_from_runtime(path, tmp_path)
                content = Path(tmp_path).read_text(
                    encoding="utf-8", errors="replace"
                )
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            lines = content.splitlines()
            sliced = lines[offset: offset + limit]
            return "\n".join(
                f"{offset + i + 1:5d} | {l}"
                for i, l in enumerate(sliced)
            )

        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str) -> str:
        """
        写本地临时文件后通过 copy_to_runtime 上传到容器。

        Returns:
            确认信息字符串。
        """
        self._assert_running()

        def _write() -> str:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".txt", mode="w", encoding="utf-8"
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                self._session.copy_to_runtime(tmp_path, path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            return f"已写入 {path}"

        return await asyncio.to_thread(_write)

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """替换文件中的指定字符串。"""
        self._assert_running()

        raw = await self._read_raw(path)
        if old_string not in raw:
            raise ValueError(f"在文件 {path!r} 中找不到要替换的字符串")

        if replace_all:
            count = raw.count(old_string)
            new_text = raw.replace(old_string, new_string)
        else:
            count = 1
            new_text = raw.replace(old_string, new_string, 1)

        await self.write_file(path, new_text)
        return f"已替换 {count} 处"

    async def list_dir(self, path: str = ".") -> str:
        """列出目录内容（ls -la）。"""
        self._assert_running()
        return await self.bash(f"ls -la {path}")

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str = "**/*",
    ) -> str:
        """在容器内搜索文件，返回最多 200 行结果。"""
        self._assert_running()
        raw = await self.bash(
            f'grep -rn --include="{glob}" "{pattern}" {path}'
        )
        lines = raw.splitlines()
        if len(lines) > 200:
            lines = lines[:200]
        return "\n".join(lines) if lines else "(无匹配)"

    # ── 命令执行 ──────────────────────────────────────────────────────

    async def bash(self, command: str, timeout: int = 30) -> str:
        """
        在容器内执行命令，返回 stdout。

        Args:
            command: Shell 命令字符串。
            timeout: 超时秒数。

        Returns:
            命令 stdout 输出。
        """
        self._assert_running()
        effective_timeout = min(timeout, self._default_timeout)

        def _exec() -> str:
            result = self._session.execute_command(command)
            return result.stdout if result.stdout else ""

        return await asyncio.wait_for(
            asyncio.to_thread(_exec),
            timeout=effective_timeout,
        )

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _assert_running(self) -> None:
        if not self.is_running():
            raise RuntimeError("LLMSandboxAdapter 未运行，请先调用 start()")

    async def _read_raw(self, path: str) -> str:
        """读取容器内文件原始内容（不带行号前缀），用于 edit_file。"""
        def _read() -> str:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".txt"
            ) as tmp:
                tmp_path = tmp.name

            try:
                self._session.copy_from_runtime(path, tmp_path)
                return Path(tmp_path).read_text(
                    encoding="utf-8", errors="replace"
                )
            finally:
                Path(tmp_path).unlink(missing_ok=True)

        return await asyncio.to_thread(_read)
