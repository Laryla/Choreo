"""
DaytonaSandboxAdapter - 基于 Daytona SDK 的云端沙箱适配器。

通过 Daytona API 创建远程沙箱环境，支持文件系统操作和进程执行。
"""

import asyncio

from choreo.sandbox.base import BaseSandbox


class DaytonaSandboxAdapter(BaseSandbox):
    """
    基于 daytona SDK 的云端沙箱适配器。

    Args:
        api_key: Daytona API 密钥（必填）。
        api_url: Daytona API 地址，默认 'https://app.daytona.io/api'。
        target:  目标区域，默认 'us'。
        timeout: bash 命令的默认超时秒数，默认 120。
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://app.daytona.io/api",
        target: str = "us",
        timeout: int = 120,
        **_kwargs,
    ) -> None:
        try:
            from daytona import Daytona, DaytonaConfig  # noqa: F401
        except ImportError as exc:
            raise ImportError("请安装 daytona: uv add daytona") from exc

        self._api_key = api_key
        self._api_url = api_url
        self._target = target
        self._default_timeout = timeout
        self._client = None
        self._sandbox = None

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """初始化 Daytona 客户端并创建远程沙箱。"""
        from daytona import Daytona, DaytonaConfig

        def _start() -> None:
            self._client = Daytona(
                DaytonaConfig(
                    api_key=self._api_key,
                    api_url=self._api_url,
                    target=self._target,
                )
            )
            self._sandbox = self._client.create()

        await asyncio.to_thread(_start)

    async def stop(self) -> None:
        """空操作（Daytona 无暂停接口）。"""
        pass

    async def destroy(self) -> None:
        """删除远程沙箱，释放云端资源。"""
        def _destroy() -> None:
            if self._client is not None and self._sandbox is not None:
                try:
                    self._client.delete(self._sandbox)
                except Exception:
                    pass
                self._sandbox = None
                self._client = None

        await asyncio.to_thread(_destroy)

    def is_running(self) -> bool:
        return self._sandbox is not None and self._client is not None

    # ── 文件操作 ──────────────────────────────────────────────────────

    async def read_file(
        self, path: str, offset: int = 0, limit: int = 2000
    ) -> str:
        """
        通过 Daytona fs API 读取远程文件，返回带行号前缀的字符串。

        Raises:
            RuntimeError: 沙箱未运行或读取失败。
        """
        self._assert_running()

        def _read() -> str:
            raw = self._sandbox.fs.download_file(path)
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
            lines = content.splitlines()
            sliced = lines[offset: offset + limit]
            return "\n".join(
                f"{offset + i + 1:5d} | {l}"
                for i, l in enumerate(sliced)
            )

        return await asyncio.to_thread(_read)

    async def write_file(self, path: str, content: str) -> str:
        """
        通过 Daytona fs API 写入远程文件。

        Returns:
            确认信息字符串。
        """
        self._assert_running()

        def _write() -> str:
            self._sandbox.fs.upload_file(
                content.encode("utf-8") if isinstance(content, str) else content,
                path,
            )
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
        """列出远程目录内容，返回与其他 provider 一致的格式。"""
        self._assert_running()
        raw = await self.bash(
            f'find "{path}" -maxdepth 1 -mindepth 1 -printf "%y %s %f\\n" 2>/dev/null'
        )
        lines = []
        for line in raw.splitlines():
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            ftype, size, name = parts
            if ftype == "d":
                lines.append(f"D {name}/")
            else:
                try:
                    lines.append(f"F {name} ({int(size)})")
                except ValueError:
                    lines.append(f"F {name} (0)")
        return "\n".join(lines) or "(空目录)"

    async def grep(
        self,
        pattern: str,
        path: str = ".",
        glob: str = "**/*",
    ) -> str:
        """在远程沙箱中搜索文件，返回最多 200 行结果。"""
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
        在远程沙箱中执行命令，返回执行结果。

        Args:
            command: Shell 命令字符串。
            timeout: 超时秒数。

        Returns:
            命令执行结果字符串。
        """
        self._assert_running()
        effective_timeout = min(timeout, self._default_timeout)

        def _exec() -> str:
            result = self._sandbox.process.exec(
                command, timeout=effective_timeout
            )
            return result.result if result.result else ""

        return await asyncio.wait_for(
            asyncio.to_thread(_exec),
            timeout=effective_timeout + 5,  # 给网络额外 5s 缓冲
        )

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _assert_running(self) -> None:
        if not self.is_running():
            raise RuntimeError(
                "DaytonaSandboxAdapter 未运行，请先调用 start()"
            )

    async def _read_raw(self, path: str) -> str:
        """读取远程文件原始内容（不带行号前缀），用于 edit_file。"""
        def _read() -> str:
            raw = self._sandbox.fs.download_file(path)
            return raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw

        return await asyncio.to_thread(_read)
