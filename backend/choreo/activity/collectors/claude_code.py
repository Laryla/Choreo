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

_MAX_PER_PROJECT = 8_000   # 每个项目最多 8K 字符
_MAX_TOTAL = 40_000        # 所有项目合计上限


def _desensitize(text: str) -> str:
    return _SENSITIVE_RE.sub(
        lambda m: m.group(0).split("=")[0].split(":")[0] + ": <redacted>",
        text,
    )


class ClaudeCodeCollector(BaseCollector):
    """通过 claude-code-log CLI + JSONL mtime 采集 Claude Code 会话行为。"""

    def __init__(self, claude_projects_dir: Path | None = None) -> None:
        self._dir = claude_projects_dir or _DEFAULT_PROJECTS_DIR

    async def collect(self, since: datetime, max_chars: int = _MAX_TOTAL) -> str:
        if not self._dir.exists():
            return ""

        # 按最近活跃时间排序，优先采集最活跃的项目
        project_dirs = [d for d in self._dir.iterdir() if d.is_dir()]
        project_dirs.sort(key=lambda d: self._last_active(d), reverse=True)

        parts: list[str] = []
        total_chars = 0

        for project_dir in project_dirs:
            if total_chars >= max_chars:
                break

            sessions = self._recent_sessions(project_dir / "sessions-index.json", since)
            if not sessions:
                continue

            content = await self._run_cc_log(project_dir, since)
            total_msgs = sum(s.get("message_count", 0) for s in sessions)
            project_name = project_dir.name.replace("-", "/").strip("/")

            body = _desensitize(content).strip() if content.strip() else "（无详细内容）"

            # 每个项目限制字符数，防止单项目吃掉所有配额
            remaining = max_chars - total_chars - 200  # 留 header 空间
            per_limit = min(_MAX_PER_PROJECT, remaining)
            if len(body) > per_limit:
                body = body[:per_limit] + f"\n...（项目内容已截断）"

            header = f"### 项目: {project_name}（{len(sessions)} 个会话，约 {total_msgs} 条消息）"
            part = f"{header}\n\n{body}"
            parts.append(part)
            total_chars += len(part)

        if not parts:
            return ""

        start = since.strftime("%Y-%m-%d")
        end = datetime.now().strftime("%Y-%m-%d")
        result = f"=== Claude Code 会话（{start} ~ {end}）===\n\n" + "\n\n---\n\n".join(parts)
        return result

    def _last_active(self, project_dir: Path) -> float:
        """返回项目最近 JSONL 的 mtime，用于排序。"""
        try:
            jsonl_files = list(project_dir.glob("*.jsonl"))
            if not jsonl_files:
                return 0.0
            return max(f.stat().st_mtime for f in jsonl_files)
        except Exception:
            return 0.0

    def _recent_sessions(self, index_path: Path, since: datetime) -> list[dict]:
        since_ts = since.timestamp()

        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
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
            except Exception:
                pass

        # Fallback：用 JSONL 文件修改时间
        project_dir = index_path.parent
        recent_jsonl = [
            f for f in project_dir.glob("*.jsonl")
            if f.stat().st_mtime >= since_ts
        ]
        return [{"session_id": f.stem} for f in recent_jsonl]

    async def _run_cc_log(self, project_dir: Path, since: datetime) -> str:
        import tempfile
        tmp_file = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
                tmp_file = Path(f.name)

            from_date = since.strftime("%Y-%m-%d")
            proc = await asyncio.create_subprocess_exec(
                "claude-code-log",
                "--format", "md",
                "--detail", "low",
                "--compact",
                "--from-date", from_date,
                "--output", str(tmp_file),
                str(project_dir),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=60)  # 单项目 60s
            if tmp_file.exists():
                return tmp_file.read_text(encoding="utf-8", errors="replace")
            return ""
        except FileNotFoundError:
            logger.warning("claude-code-log CLI 未安装，跳过内容提取")
            return ""
        except asyncio.TimeoutError:
            logger.warning("claude-code-log 超时：%s", project_dir)
            return ""
        except Exception as exc:
            logger.warning("claude-code-log 失败：%s %r", project_dir, exc)
            return ""
        finally:
            if tmp_file and tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
