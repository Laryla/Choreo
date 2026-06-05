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
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = load_model()
            raw_excerpt = _desensitize(new_raw)[:_RAW_COMPRESS_LIMIT]

            if existing.strip():
                # 有既有摘要：合并更新模式
                system = (
                    "# Role: 工作记录压缩器\n\n"
                    "## Profile\n"
                    "面向项目工作记录的高密度摘要与更新合并专家，能够将新增会话记录精准融入既有摘要，"
                    "去重、取精、保序，在严格字数约束下输出清晰、准确、可执行的最新版本摘要。\n\n"
                    "## Skills\n"
                    "- 关键要点识别：抓取进展、决策、变更、问题/风险、行动项、里程碑、负责人、截止日期等。\n"
                    "- 去重合并：与现有摘要比对相同或相似事项，合并更新，避免重复与信息矛盾。\n"
                    "- 冲突解析：对版本差异与口径冲突，优先采用更近时点、更具体的数据与结论。\n"
                    "- 结构对齐：继承现有摘要的叙述风格（条目/段落/分号短句），术语、格式保持一致。\n"
                    "- 噪声过滤：去除寒暄、情绪性与无信息量内容，仅保留与项目相关的事实与结论。\n\n"
                    "## Rules\n"
                    "- 准确性优先：仅基于输入的明确信息整合，不臆测、不扩写。\n"
                    "- 直接输出摘要：不添加标题、前缀、后缀、解释或致谢，不输出「摘要：」等引导词。\n"
                    "- 客观中性：使用客观表述，避免主观评价或无依据的判断。\n"
                    "- 不新增信息：不补充缺失背景，不推断不可证实的因果或数据。\n"
                    f"- 严格字数：最终输出必须 ≤ {_SUMMARY_MAX} 字，必要时按重要性裁剪。\n\n"
                    "## Workflow\n"
                    "1. 解析输入：识别项目范围与上下文，从新增记录提取进展、决策、问题/风险、行动项。\n"
                    "2. 合并去重：对齐同一事项，保留更具体与更新的内容，时间上以近期为准。\n"
                    "3. 压缩编排：优先呈现决策/里程碑、严重问题、关键行动项；使用紧凑短句或分号条目；"
                    f"确保 ≤ {_SUMMARY_MAX} 字。"
                )
                user = (
                    f"项目：{project_name}\n\n"
                    f"【现有摘要】\n{existing}\n\n"
                    f"【新增会话记录】\n{raw_excerpt}"
                )
            else:
                # 无既有摘要：首次压缩模式
                system = (
                    "# Role: 工作记录摘要压缩器\n\n"
                    "## Profile\n"
                    "面向项目会话/工作记录的高密度摘要器，专注在限定字数内提炼"
                    "「做了什么、遇到什么问题、用了什么技术」三要素，输出直接可用的简洁摘要。\n\n"
                    "## Skills\n"
                    "- 关键信息抽取：从原文中定位「行动/产出、问题/阻碍、技术/工具/方案」。\n"
                    f"- 字数与密度控制：严格控制在 {_SUMMARY_MAX} 字以内，使用高信息密度短句。\n"
                    "- 术语标准化：将口语与零散描述规范为专业、统一的术语表达。\n"
                    "- 去噪与去重：删除寒暄、重复、离题内容，合并同类项。\n\n"
                    "## Rules\n"
                    "- 三要素覆盖：摘要需覆盖「做了什么、遇到的问题、使用的技术」；若某项未出现，用「未提及」占位。\n"
                    f"- 最大长度：最终输出字符总数（含标点与空格）必须 ≤ {_SUMMARY_MAX}。\n"
                    "- 原文忠实：仅依据输入内容，不引入外部知识或主观判断。\n"
                    "- 输出格式：直接输出摘要正文，不添加标题、前缀、序号、解释或致谢。\n"
                    "- 无项目符号：不使用条目符号或编号，以句式或分号分隔信息。\n"
                    "- 空内容策略：若输入缺乏有效信息，输出「无有效内容」。\n\n"
                    "## Workflow\n"
                    "1. 通读输入，快速标注三要素：行动/产出、问题/阻碍、技术/工具/方案；记录关键名词、数值、时间点。\n"
                    "2. 去除寒暄、重复与无关讨论；合并同类信息，统一术语与时态。\n"
                    f"3. 以并列短句形成「完成…；问题：…；技术：…」或等效紧凑结构；核对三要素覆盖；确保 ≤ {_SUMMARY_MAX} 字。"
                )
                user = (
                    f"项目：{project_name}\n\n"
                    f"【会话记录】\n{raw_excerpt}"
                )

            resp = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=user)])
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
