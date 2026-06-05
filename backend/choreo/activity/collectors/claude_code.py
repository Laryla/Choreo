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

# 单项目压缩后上限
_SUMMARY_MAX = 600
# 送给 LLM 压缩的原始内容上限（避免超 context）
_RAW_COMPRESS_LIMIT = 15_000


def _desensitize(text: str) -> str:
    return _SENSITIVE_RE.sub(
        lambda m: m.group(0).split("=")[0].split(":")[0] + ": <redacted>",
        text,
    )


class ClaudeCodeCollector(BaseCollector):
    """增量采集 Claude Code 会话，逐项目 LLM 压缩后存档，每次返回全量摘要。"""

    def __init__(self, claude_projects_dir: Path | None = None) -> None:
        self._dir = claude_projects_dir or _DEFAULT_PROJECTS_DIR
        from choreo.config import settings
        kb_root = Path(settings.KNOWLEDGE_BASE_DIR).expanduser()
        self._summary_dir = kb_root / "raw" / "cc-summaries"
        self._meta_file = self._summary_dir / ".meta.json"

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    async def collect(self, since: datetime, max_chars: int = 0) -> str:
        """增量更新各项目摘要，返回全量摘要拼合字符串。since/max_chars 已由内部 meta 管理。"""
        del since, max_chars  # 时间窗口改由 meta 中的 last_summarized 管理
        if not self._dir.exists():
            return ""

        self._summary_dir.mkdir(parents=True, exist_ok=True)
        meta = self._load_meta()

        project_dirs = sorted(
            [d for d in self._dir.iterdir() if d.is_dir()],
            key=lambda d: self._last_active(d),
            reverse=True,
        )

        any_updated = False
        for project_dir in project_dirs:
            updated = await self._update_project(project_dir, meta)
            if updated:
                any_updated = True

        if any_updated:
            self._save_meta(meta)

        return self._build_output(project_dirs)

    # ------------------------------------------------------------------
    # 增量更新单个项目
    # ------------------------------------------------------------------

    async def _update_project(self, project_dir: Path, meta: dict) -> bool:
        proj_key = project_dir.name

        # 检查是否有新会话
        last_summarized = meta.get(proj_key, {}).get("last_summarized", 0.0)
        last_active = self._last_active(project_dir)
        if last_active <= last_summarized:
            return False

        last_dt = datetime.fromtimestamp(last_summarized) if last_summarized else datetime(2020, 1, 1)
        sessions = self._recent_sessions(project_dir / "sessions-index.json", last_dt)
        if not sessions:
            return False

        raw = await self._run_cc_log(project_dir, last_dt)
        if not raw.strip():
            return False

        summary_path = self._summary_dir / f"{proj_key}.md"
        existing = summary_path.read_text(encoding="utf-8", errors="replace") if summary_path.exists() else ""

        project_name = proj_key.replace("-", "/").strip("/")
        new_summary = await self._compress(project_name, raw, existing)

        summary_path.write_text(new_summary, encoding="utf-8")
        meta.setdefault(proj_key, {})["last_summarized"] = datetime.now().timestamp()
        logger.info("已更新项目摘要：%s", project_name)
        return True

    # ------------------------------------------------------------------
    # LLM 压缩
    # ------------------------------------------------------------------

    async def _compress(self, project_name: str, new_raw: str, existing: str) -> str:
        try:
            from choreo.model_factory import load_model
            from langchain_core.messages import HumanMessage

            llm = load_model()
            raw_excerpt = _desensitize(new_raw)[:_RAW_COMPRESS_LIMIT]

            if existing.strip():
                prompt = (
                    f"你是工作记录压缩器。\n\n"
                    f"【现有摘要】（{project_name} 项目）：\n{existing}\n\n"
                    f"【新增会话记录】：\n{raw_excerpt}\n\n"
                    f"将新记录融入现有摘要，保留所有重要工作内容，控制在 {_SUMMARY_MAX} 字以内。"
                    f"直接输出摘要，不要前缀。"
                )
            else:
                prompt = (
                    f"你是工作记录压缩器。\n\n"
                    f"【会话记录】（{project_name} 项目）：\n{raw_excerpt}\n\n"
                    f"用 {_SUMMARY_MAX} 字以内总结：做了什么、遇到什么问题、用了什么技术。"
                    f"直接输出摘要，不要前缀。"
                )

            resp = await llm.ainvoke([HumanMessage(content=prompt)])
            return str(resp.content).strip()

        except Exception as exc:
            logger.warning("LLM 压缩失败 %s: %r，回退到截断", project_name, exc)
            return _desensitize(new_raw)[:_SUMMARY_MAX * 4]

    # ------------------------------------------------------------------
    # 拼合输出
    # ------------------------------------------------------------------

    def _build_output(self, project_dirs: list[Path]) -> str:
        parts: list[str] = []
        for project_dir in project_dirs:
            summary_path = self._summary_dir / f"{project_dir.name}.md"
            if not summary_path.exists():
                continue
            content = summary_path.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                continue
            project_name = project_dir.name.replace("-", "/").strip("/")
            parts.append(f"### {project_name}\n\n{content}")

        if not parts:
            return ""

        return "=== Claude Code 项目摘要 ===\n\n" + "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _load_meta(self) -> dict:
        if self._meta_file.exists():
            try:
                return json.loads(self._meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_meta(self, meta: dict) -> None:
        self._meta_file.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _last_active(self, project_dir: Path) -> float:
        try:
            files = list(project_dir.glob("*.jsonl"))
            return max((f.stat().st_mtime for f in files), default=0.0)
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

        project_dir = index_path.parent
        recent = [f for f in project_dir.glob("*.jsonl") if f.stat().st_mtime >= since_ts]
        return [{"session_id": f.stem} for f in recent]

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
            await asyncio.wait_for(proc.communicate(), timeout=60)
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
