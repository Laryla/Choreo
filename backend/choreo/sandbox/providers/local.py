"""
LocalSandbox - 本地文件系统沙箱实现。

在宿主机的 workspace_dir 目录中执行文件操作和 bash 命令。
所有路径操作均受 workspace_dir 限制（路径越界时抛出 PermissionError）。
"""

import asyncio
import os
import re
import subprocess
from pathlib import Path

from choreo.sandbox.base import BaseSandbox


class LocalSandbox(BaseSandbox):
    """
    基于本地文件系统的沙箱。

    Args:
        workspace_dir: 工作目录路径（相对或绝对），默认 './sandbox'。
        timeout:       bash 命令的默认超时秒数，默认 120。
    """

    def __init__(
        self,
        workspace_dir: str = "./sandbox",
        timeout: int = 120,
        skills_dir: str | None = None,
        **_kwargs,
    ) -> None:
        self._workspace = Path(workspace_dir)
        self._default_timeout = timeout
        self._skills_dir = Path(skills_dir).resolve() if skills_dir else None
        self._running = False

    # ── 路径安全 ──────────────────────────────────────────────────────

    def _validate_path(self, path: str) -> Path:
        """
        解析并校验路径不超出 workspace 根目录。

        Returns:
            解析后的绝对 Path 对象。

        Raises:
            PermissionError: 路径解析后逃逸到 workspace 外部。
        """
        root = self._workspace.resolve()
        candidate = (root / path).resolve()
        if not str(candidate).startswith(str(root)):
            raise PermissionError(f"路径越界: {path}")
        return candidate

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """创建 workspace 目录，软链 skills 目录，标记为运行状态。"""
        await asyncio.to_thread(self._workspace.mkdir, parents=True, exist_ok=True)
        if self._skills_dir and self._skills_dir.exists():
            link = self._workspace.resolve() / ".skills"
            if not link.exists():
                await asyncio.to_thread(link.symlink_to, self._skills_dir)
        self._running = True

    async def stop(self) -> None:
        """空操作（本地沙箱无需暂停）。"""
        pass

    async def destroy(self) -> None:
        """仅标记为已停止，不删除目录（防止意外数据丢失）。"""
        self._running = False

    def is_running(self) -> bool:
        return self._running

    # ── 文件操作 ──────────────────────────────────────────────────────

    async def read_file(
        self, path: str, offset: int = 0, limit: int = 2000
    ) -> str:
        """
        读取文件指定行范围，返回带行号前缀的字符串。

        Args:
            path:   相对于 workspace 的文件路径。
            offset: 从第几行开始（0 索引）。
            limit:  最多读取行数，默认 2000。

        Returns:
            带行号前缀的文本，格式：`"    1 | line content"`。

        Raises:
            FileNotFoundError: 文件不存在。
            IsADirectoryError: 路径是目录。
        """
        abs_path = self._validate_path(path)

        def _read() -> str:
            if not abs_path.exists():
                raise FileNotFoundError(f"文件不存在: {path}")
            if abs_path.is_dir():
                raise IsADirectoryError(f"路径是目录: {path}")
            text = abs_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            window = lines[offset: offset + limit]
            return "\n".join(
                f"{offset + i + 1:5d} | {line}"
                for i, line in enumerate(window)
            )

        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str) -> str:
        """
        写入文件（不存在则创建，存在则覆盖）。

        Returns:
            确认信息字符串。
        """
        abs_path = self._validate_path(path)

        def _write() -> str:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(content, encoding="utf-8")
            return f"已写入 {abs_path}"

        return await asyncio.to_thread(_write)

    async def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        """
        替换文件中的指定字符串。

        Args:
            replace_all: True 替换全部出现，False 只替换第一个。

        Returns:
            确认信息，包含替换次数。

        Raises:
            FileNotFoundError: 文件不存在。
            ValueError:        old_string 在文件中不存在。
        """
        abs_path = self._validate_path(path)

        def _edit() -> str:
            if not abs_path.exists():
                raise FileNotFoundError(f"文件不存在: {path}")
            text = abs_path.read_text(encoding="utf-8")
            if old_string not in text:
                raise ValueError(
                    f"在文件 {path!r} 中找不到要替换的字符串"
                )
            if replace_all:
                count = text.count(old_string)
                new_text = text.replace(old_string, new_string)
            else:
                count = 1
                new_text = text.replace(old_string, new_string, 1)
            abs_path.write_text(new_text, encoding="utf-8")
            return f"已替换 {count} 处"

        return await asyncio.to_thread(_edit)

    async def list_dir(self, path: str = ".") -> str:
        """
        列出目录内容。

        格式：
          `D dirname/`   — 子目录
          `F filename (size)` — 文件（显示字节数）

        Raises:
            FileNotFoundError: 路径不存在。
            NotADirectoryError: 路径不是目录。
        """
        abs_path = self._validate_path(path)

        def _list() -> str:
            if not abs_path.exists():
                raise FileNotFoundError(f"路径不存在: {path}")
            if not abs_path.is_dir():
                raise NotADirectoryError(f"路径不是目录: {path}")
            entries = sorted(abs_path.iterdir(), key=lambda p: (p.is_file(), p.name))
            lines = []
            for entry in entries:
                if entry.is_dir():
                    lines.append(f"D {entry.name}/")
                else:
                    size = entry.stat().st_size
                    lines.append(f"F {entry.name} ({size})")
            return "\n".join(lines) if lines else "(空目录)"

        return await asyncio.to_thread(_list)

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str = "**/*",
    ) -> str:
        """
        在目录下的文件中正则搜索。

        返回格式：`file_rel:lineno:line_content`，最多 200 条结果。

        Raises:
            FileNotFoundError: 搜索路径不存在。
            re.error: pattern 不是合法正则。
        """
        abs_path = self._validate_path(path)
        root = self._workspace.resolve()

        def _grep() -> str:
            if not abs_path.exists():
                raise FileNotFoundError(f"路径不存在: {path}")
            regex = re.compile(pattern)
            results: list[str] = []
            for file_path in sorted(abs_path.glob(glob)):
                if not file_path.is_file():
                    continue
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                rel = file_path.relative_to(root)
                for lineno, line in enumerate(text.splitlines(), start=1):
                    if regex.search(line):
                        results.append(f"{rel}:{lineno}:{line}")
                        if len(results) >= 200:
                            return "\n".join(results)
            return "\n".join(results) if results else "(无匹配)"

        return await asyncio.to_thread(_grep)

    # ── 命令执行 ──────────────────────────────────────────────────────

    async def bash(self, command: str, timeout: int = 30) -> str:
        """
        在 workspace 目录中执行 bash 命令。

        Args:
            command: Shell 命令字符串。
            timeout: 超时秒数（默认 30，不超过构造时设定的 _default_timeout）。

        Returns:
            stdout（非空时）或 stderr。

        Raises:
            TimeoutError: 命令超时。
        """
        effective_timeout = min(timeout, self._default_timeout)

        env = {**os.environ, "SKILLS_DIR": str(self._skills_dir)} if self._skills_dir else None

        def _run() -> str:
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=self._workspace,
                    timeout=effective_timeout,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                return result.stdout if result.stdout else result.stderr
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(
                    f"命令超时（{effective_timeout}s）：{command}"
                ) from exc

        return await asyncio.to_thread(_run)
