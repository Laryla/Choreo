from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from choreo.activity.collectors.base import BaseCollector

logger = logging.getLogger(__name__)

_DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"

_SENSITIVE_RE = re.compile(
    r"(api[_-]?key|token|password|secret|credential|authorization)[^\n]*",
    re.IGNORECASE,
)


def _desensitize(text: str) -> str:
    return _SENSITIVE_RE.sub(
        lambda m: m.group(0).split("=")[0].split(":")[0] + ": <redacted>",
        text,
    )


class ClaudeCodeCollector(BaseCollector):
    """通过 claude-code-log CLI + sessions-index.json 采集 Claude Code 会话行为。"""

    def __init__(self, claude_projects_dir: Path | None = None) -> None:
        self._dir = claude_projects_dir or _DEFAULT_PROJECTS_DIR

    async def collect(self, since: datetime) -> str:
        if not self._dir.exists():
            return ""

        parts: list[str] = []

        for project_dir in sorted(self._dir.iterdir()):
            if not project_dir.is_dir():
                continue

            sessions = self._recent_sessions(project_dir / "sessions-index.json", since)
            if not sessions:
                continue

            content = await self._run_cc_log(project_dir)
            total_msgs = sum(s.get("message_count", 0) for s in sessions)
            project_name = project_dir.name.replace("-", "/").strip("/")

            header = f"### 项目: {project_name}（{len(sessions)} 个会话，约 {total_msgs} 条消息）"
            body = _desensitize(content) if content.strip() else "（无详细内容）"
            parts.append(f"{header}\n\n{body}")

        if not parts:
            return ""

        start = since.strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        return f"=== Claude Code 会话（{start} ~ {end}）===\n\n" + "\n\n---\n\n".join(parts)

    def _recent_sessions(self, index_path: Path, since: datetime) -> list[dict]:
        if not index_path.exists():
            return []
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        since_ts = since.timestamp()
        result = []
        for s in data if isinstance(data, list) else []:
            raw = s.get("updated_at", 0)
            if isinstance(raw, str):
                try:
                    ts = datetime.fromisoformat(raw).timestamp()
                except ValueError:
                    continue
            else:
                ts = float(raw)
            if ts >= since_ts:
                result.append(s)
        return result

    async def _run_cc_log(self, project_dir: Path) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude-code-log",
                "--format", "md",
                "--detail", "low",
                "--compact",
                str(project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            return stdout.decode("utf-8", errors="replace")
        except FileNotFoundError:
            logger.warning("claude-code-log CLI 未安装，跳过内容提取")
            return ""
        except asyncio.TimeoutError:
            logger.warning("claude-code-log 超时：%s", project_dir)
            return ""
        except Exception as exc:
            logger.warning("claude-code-log 失败：%s %r", project_dir, exc)
            return ""
