"""
DockerSandbox - 基于 Docker SDK 的容器沙箱实现。

在独立 Docker 容器中执行文件操作和 bash 命令，
本地临时目录通过 volume 挂载进容器。
"""

import asyncio
import io
import os
import tarfile
import tempfile
from pathlib import Path

from choreo.sandbox.base import BaseSandbox


class DockerSandbox(BaseSandbox):
    """
    基于 docker SDK 的沙箱实现。

    Args:
        image:         Docker 镜像，默认 'python:3.11-slim'。
        workspace_dir: 容器内工作目录，默认 '/workspace'。
        timeout:       bash 命令的默认超时秒数，默认 60。
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        workspace_dir: str = "/workspace",
        timeout: int = 60,
        **_kwargs,
    ) -> None:
        try:
            import docker  # noqa: F401
        except ImportError as exc:
            raise ImportError("请安装 docker: uv add docker") from exc

        self._image = image
        self._workspace_dir = workspace_dir
        self._default_timeout = timeout
        self._container = None
        self._tmp_dir: tempfile.TemporaryDirectory | None = None

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """创建本地临时目录，挂载进容器并以 sleep infinity 启动。"""
        import docker

        def _start() -> None:
            self._tmp_dir = tempfile.TemporaryDirectory(prefix="choreo_docker_")
            client = docker.from_env()
            self._container = client.containers.run(
                self._image,
                detach=True,
                command="sleep infinity",
                volumes={
                    self._tmp_dir.name: {
                        "bind": self._workspace_dir,
                        "mode": "rw",
                    }
                },
                working_dir=self._workspace_dir,
            )

        await asyncio.to_thread(_start)

    async def stop(self) -> None:
        """暂停容器（保留状态，可用 start() 恢复）。"""
        if self._container is None:
            raise RuntimeError("沙箱未启动")

        def _stop() -> None:
            self._container.stop(timeout=5)

        await asyncio.to_thread(_stop)

    async def destroy(self) -> None:
        """停止并删除容器，清理临时目录。"""
        def _destroy() -> None:
            if self._container is not None:
                try:
                    self._container.stop(timeout=5)
                except Exception:
                    pass
                try:
                    self._container.remove(force=True)
                except Exception:
                    pass
                self._container = None
            if self._tmp_dir is not None:
                try:
                    self._tmp_dir.cleanup()
                except Exception:
                    pass
                self._tmp_dir = None

        await asyncio.to_thread(_destroy)

    def is_running(self) -> bool:
        if self._container is None:
            return False
        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False

    # ── 文件操作 ──────────────────────────────────────────────────────

    async def read_file(
        self, path: str, offset: int = 0, limit: int = 2000
    ) -> str:
        """
        读取容器内文件指定行范围，返回带行号前缀的字符串。

        Raises:
            RuntimeError: 沙箱未运行或命令执行失败。
        """
        self._assert_running()

        def _read() -> str:
            result = self._container.exec_run(
                f"cat {path}",
                workdir=self._workspace_dir,
            )
            output = result.output.decode("utf-8", errors="replace")
            lines = output.splitlines()
            window = lines[offset: offset + limit]
            return "\n".join(
                f"{offset + i + 1:5d} | {line}"
                for i, line in enumerate(window)
            )

        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str) -> str:
        """
        将内容写入容器内文件（通过 put_archive 上传）。

        Returns:
            确认信息字符串。
        """
        self._assert_running()

        def _write() -> str:
            # 构建内存 tar 包，通过 put_archive 上传
            file_name = os.path.basename(path)
            dir_path = os.path.dirname(path)
            if not dir_path:
                dir_path = self._workspace_dir
            elif not dir_path.startswith("/"):
                dir_path = os.path.join(self._workspace_dir, dir_path)

            data = content.encode("utf-8")
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                info = tarfile.TarInfo(name=file_name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            buf.seek(0)

            # 确保目标目录存在
            self._container.exec_run(
                f"mkdir -p {dir_path}",
                workdir=self._workspace_dir,
            )
            self._container.put_archive(dir_path, buf.read())
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

        # 读取原始内容（不带行号）
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
        """列出容器内目录内容（ls -la）。"""
        self._assert_running()
        target = path if path.startswith("/") else os.path.join(self._workspace_dir, path)
        return await self.bash(f"ls -la {target}")

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str = "**/*",
    ) -> str:
        """在容器内搜索文件，返回最多 200 行结果。"""
        self._assert_running()
        target = path if path.startswith("/") else os.path.join(self._workspace_dir, path)

        def _grep() -> str:
            result = self._container.exec_run(
                f'grep -rn --include="{glob}" "{pattern}" {target}',
                workdir=self._workspace_dir,
            )
            output = result.output.decode("utf-8", errors="replace")
            lines = output.splitlines()
            if len(lines) > 200:
                lines = lines[:200]
            return "\n".join(lines) if lines else "(无匹配)"

        return await asyncio.to_thread(_grep)

    # ── 命令执行 ──────────────────────────────────────────────────────

    async def bash(self, command: str, timeout: int = 30) -> str:
        """
        在容器内执行 bash 命令。

        Args:
            command: Shell 命令字符串。
            timeout: 超时秒数。

        Returns:
            命令输出（stdout + stderr 合并）。
        """
        self._assert_running()
        effective_timeout = min(timeout, self._default_timeout)

        def _exec() -> str:
            result = self._container.exec_run(
                f"bash -c '{command}'",
                workdir=self._workspace_dir,
            )
            return result.output.decode("utf-8", errors="replace")

        return await asyncio.wait_for(
            asyncio.to_thread(_exec),
            timeout=effective_timeout,
        )

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _assert_running(self) -> None:
        if not self.is_running():
            raise RuntimeError("DockerSandbox 未运行，请先调用 start()")

    async def _read_raw(self, path: str) -> str:
        """读取容器内文件原始内容（不带行号前缀）。"""
        def _read() -> str:
            result = self._container.exec_run(
                f"cat {path}",
                workdir=self._workspace_dir,
            )
            return result.output.decode("utf-8", errors="replace")

        return await asyncio.to_thread(_read)
