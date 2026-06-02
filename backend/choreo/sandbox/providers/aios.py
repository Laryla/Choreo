"""
AiosSandbox - 基于 AIO Sandbox (agent-infra) 的沙箱实现。

通过 agent-sandbox SDK 与运行中的 AIO Sandbox 容器通信。
支持两种模式：
  1. 自动模式（auto_start=True）：自动拉起本地 Docker 容器，用完自动销毁
  2. 连接模式（base_url=...）：连接到已有的 AIO Sandbox 实例

安装依赖：uv add agent-sandbox docker
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from choreo.sandbox.base import BaseSandbox

logger = logging.getLogger(__name__)

_DEFAULT_IMAGE = "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/all-in-one-sandbox"
_CONTAINER_PORT = 8080
_STARTUP_TIMEOUT = 60  # 容器启动等待秒数


class AiosSandbox(BaseSandbox):
    """
    AIO Sandbox provider。

    Args:
        image:       Docker 镜像，默认使用 all-in-one-sandbox。
        host_port:   宿主机映射端口，0 表示随机分配（auto_start 模式）。
        base_url:    直接连接已有实例（设置后跳过 Docker 管理）。
        workspace_dir: 容器内工作目录，默认 /home/user。
        timeout:     bash 命令默认超时秒数。
        auto_start:  是否在 start() 时自动拉起 Docker 容器。
    """

    def __init__(
        self,
        image: str = _DEFAULT_IMAGE,
        host_port: int = 0,
        base_url: str | None = None,
        workspace_dir: str = "/home/user",
        timeout: int = 60,
        auto_start: bool = True,
        skills_dir: str | None = None,
        output_dir: str | None = None,
        container_name: str | None = None,
        **_kwargs: Any,
    ) -> None:
        self._image = image
        self._host_port = host_port
        self._base_url = base_url
        self._workspace_dir = workspace_dir
        self._default_timeout = timeout
        self._auto_start = auto_start
        self._skills_dir = Path(skills_dir).resolve() if skills_dir else None
        self._output_dir = Path(output_dir).resolve() if output_dir else None
        self._container_name = container_name

        self._container = None
        self._client = None  # AsyncSandbox instance

    # ── 生命周期 ──────────────────────────────────────────────────────

    async def start(self) -> None:
        try:
            from agent_sandbox import AsyncSandbox
        except ImportError as exc:
            raise ImportError("请安装 agent-sandbox: uv add agent-sandbox") from exc

        if self._base_url:
            self._client = AsyncSandbox(base_url=self._base_url)
            return

        if not self._auto_start:
            raise RuntimeError("未设置 base_url 且 auto_start=False，无法启动沙箱")

        try:
            import docker
        except ImportError as exc:
            raise ImportError("请安装 docker: uv add docker") from exc

        _container_name = self._container_name or "choreo-aios-sandbox"
        logger.info("[sandbox] start requested: container=%s", _container_name)
        _t0 = time.monotonic()

        def _start() -> str:
            client = docker.from_env()
            # Reuse existing container if already running
            try:
                existing = client.containers.get(_container_name)
                existing.reload()
                if existing.status == "running":
                    bindings = existing.ports.get(f"{_CONTAINER_PORT}/tcp") or []
                    if bindings:
                        logger.info("[sandbox] reusing running container: %s port=%s", _container_name, bindings[0]["HostPort"])
                        self._container = existing
                        return f"http://localhost:{bindings[0]['HostPort']}"
                # Stopped but not removed — restart it
                logger.info("[sandbox] restarting stopped container: %s", _container_name)
                existing.start()
                existing.reload()
                self._container = existing
                bindings = existing.ports.get(f"{_CONTAINER_PORT}/tcp") or []
                if bindings:
                    return f"http://localhost:{bindings[0]['HostPort']}"
            except Exception:
                pass  # Container doesn't exist, create it

            logger.info("[sandbox] creating new container: %s image=%s", _container_name, self._image)
            port_binding = self._host_port or None
            volumes: dict = {}
            environment: dict = {}
            # Mount outside /home/gem to avoid interfering with container init
            if self._skills_dir and self._skills_dir.exists():
                volumes[str(self._skills_dir)] = {"bind": "/choreo-skills", "mode": "ro"}
                environment["SKILLS_DIR"] = "/choreo-skills"
            if self._output_dir:
                self._output_dir.mkdir(parents=True, exist_ok=True)
                volumes[str(self._output_dir)] = {"bind": "/choreo-output", "mode": "rw"}
                environment["OUTPUT_DIR"] = "/choreo-output"
            container = client.containers.run(
                self._image,
                name=_container_name,
                detach=True,
                security_opt=["seccomp=unconfined"],
                ports={f"{_CONTAINER_PORT}/tcp": port_binding},
                volumes=volumes or None,
                environment=environment or None,
            )
            self._container = container
            for _ in range(20):
                time.sleep(0.5)
                try:
                    container.reload()
                except Exception:
                    logs = ""
                    try:
                        logs = container.logs().decode("utf-8", errors="replace")[-500:]
                    except Exception:
                        pass
                    raise RuntimeError(f"容器意外退出。最近日志：\n{logs}")
                bindings = container.ports.get(f"{_CONTAINER_PORT}/tcp") or []
                if bindings:
                    break
            bindings = container.ports.get(f"{_CONTAINER_PORT}/tcp") or []
            if not bindings:
                raise RuntimeError("容器端口映射未就绪")
            port = bindings[0]["HostPort"]
            return f"http://localhost:{port}"

        base_url = await asyncio.to_thread(_start)
        from agent_sandbox import AsyncSandbox
        self._client = AsyncSandbox(base_url=base_url)
        await self._wait_ready()
        elapsed = time.monotonic() - _t0
        logger.info("[sandbox] ready: container=%s url=%s elapsed=%.1fs", _container_name, base_url, elapsed)
        # Create symlinks inside workspace after init completes
        if self._skills_dir:
            await self.bash(f"ln -sfn /choreo-skills {self._workspace_dir}/.skills 2>/dev/null || true")
        if self._output_dir:
            await self.bash(f"mkdir -p /choreo-output && ln -sfn /choreo-output {self._workspace_dir}/output 2>/dev/null || true")

    async def stop(self) -> None:
        if self._container is not None:
            logger.info("[sandbox] stopping container: %s", self._container.name)
            def _stop() -> None:
                self._container.stop(timeout=5)
            await asyncio.to_thread(_stop)
            logger.info("[sandbox] container stopped: %s", self._container.name)

    async def destroy(self) -> None:
        if self._container is not None:
            name = self._container.name
            logger.info("[sandbox] destroying container: %s", name)
            def _destroy() -> None:
                try:
                    self._container.stop(timeout=5)
                except Exception:
                    pass
                try:
                    self._container.remove(force=True)
                except Exception:
                    pass
            await asyncio.to_thread(_destroy)
            logger.info("[sandbox] container destroyed: %s", name)
            self._container = None
        self._client = None

    def is_running(self) -> bool:
        if self._base_url:
            return self._client is not None
        if self._container is None:
            return False
        try:
            self._container.reload()
            return self._container.status == "running"
        except Exception:
            return False

    # ── 文件操作 ──────────────────────────────────────────────────────

    async def read_file(self, path: str, offset: int = 0, limit: int = 2000) -> str:
        self._assert_client()
        resp = await self._client.file.read_file(
            file=self._abs(path),
            start_line=offset,
            end_line=offset + limit,
        )
        content = resp.data.content if resp.data else ""
        lines = content.splitlines()
        return "\n".join(f"{offset + i + 1:5d} | {line}" for i, line in enumerate(lines))

    async def write_file(self, path: str, content: str) -> str:
        self._assert_client()
        await self._client.file.write_file(file=self._abs(path), content=content)
        return f"已写入 {path}"

    async def edit_file(
        self, path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        self._assert_client()
        if replace_all:
            resp = await self._client.file.read_file(file=self._abs(path))
            raw = resp.data.content if resp.data else ""
            if old_string not in raw:
                raise ValueError(f"在文件 {path!r} 中找不到要替换的字符串")
            count = raw.count(old_string)
            new_text = raw.replace(old_string, new_string)
            await self._client.file.write_file(file=self._abs(path), content=new_text)
            return f"已替换 {count} 处"
        else:
            await self._client.file.replace_in_file(
                file=self._abs(path),
                old_str=old_string,
                new_str=new_string,
            )
            return "已替换 1 处"

    async def list_dir(self, path: str = ".") -> str:
        self._assert_client()
        resp = await self._client.file.list_path(path=self._abs(path))
        files = (resp.data.files or []) if resp.data else []
        lines = []
        for f in files:
            ftype = "d" if f.is_directory else "-"
            size = str(f.size or 0)
            lines.append(f"{ftype}  {size:>10}  {f.name}")
        return "\n".join(lines) or "(空目录)"

    async def grep(self, pattern: str, path: str = ".", glob: str = "**/*") -> str:
        self._assert_client()
        target = self._abs(path)
        # 用 shell grep 代替 SDK grep_files（更兼容）
        include_flag = f'--include="{glob}"' if glob and glob != "**/*" else ""
        cmd = f'grep -rn {include_flag} "{pattern}" "{target}" 2>/dev/null | head -200'
        resp = await self._client.shell.exec_command(command=cmd)
        output = (resp.data.output or "") if resp.data else ""
        return output.strip() or "(无匹配)"

    # ── 命令执行 ──────────────────────────────────────────────────────

    async def bash(self, command: str, timeout: int = 30) -> str:
        self._assert_client()
        effective = min(timeout, self._default_timeout)
        resp = await asyncio.wait_for(
            self._client.shell.exec_command(command=command, timeout=float(effective)),
            timeout=effective + 5,
        )
        output = (resp.data.output or "") if resp.data else ""
        return output.strip()

    # ── 内部工具 ──────────────────────────────────────────────────────

    def _assert_client(self) -> None:
        if self._client is None:
            raise RuntimeError("AiosSandbox 未启动，请先调用 start()")

    def _abs(self, path: str) -> str:
        if path.startswith("/"):
            return path
        if path in (".", ""):
            return self._workspace_dir
        return f"{self._workspace_dir.rstrip('/')}/{path}"

    async def _wait_ready(self, interval: float = 1.0) -> None:
        import httpx
        base_url = getattr(self._client, "_base_url", None) or getattr(self._client, "base_url", "")
        if not base_url:
            await asyncio.sleep(3)
            return

        deadline = time.monotonic() + _STARTUP_TIMEOUT
        async with httpx.AsyncClient() as http:
            while time.monotonic() < deadline:
                try:
                    r = await http.get(f"{base_url}/v1/docs", timeout=2)
                    if r.status_code < 500:
                        return
                except Exception:
                    pass
                await asyncio.sleep(interval)

        raise RuntimeError(f"AIO Sandbox 在 {_STARTUP_TIMEOUT}s 内未就绪，请检查容器日志")
