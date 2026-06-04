from pathlib import Path

from langchain_core.tools import tool

from choreo.config import settings


def _kb_root() -> Path:
    return Path(settings.KNOWLEDGE_BASE_DIR)


def _wiki_dir() -> Path:
    return _kb_root() / "wiki"


def _raw_dir() -> Path:
    return _kb_root() / "raw"


@tool
async def kb_grep(query: str, limit: int = 10) -> str:
    """搜索 wiki 页面中的关键词，返回匹配行及页面名、行号。

    Args:
        query: 要搜索的关键词（大小写不敏感）。
        limit: 最多返回的匹配行数（默认 10）。

    Returns:
        匹配行，格式为 'page_path:行号: 行内容'；或无结果提示信息。
    """
    wiki_dir = _wiki_dir()
    if not wiki_dir.exists():
        return "知识库尚未初始化，未找到 wiki 页面。"

    results: list[str] = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        page = str(md_file.relative_to(wiki_dir))
        for i, line in enumerate(md_file.read_text(errors="replace").splitlines(), 1):
            if query.lower() in line.lower():
                results.append(f"{page}:{i}: {line.strip()}")
                if len(results) >= limit:
                    return "\n".join(results)

    return "\n".join(results) if results else f"No results found for '{query}'."


@tool
async def kb_read(page_path: str) -> str:
    """读取 wiki/ 目录下指定路径的页面内容。

    Args:
        page_path: 相对于 wiki/ 的路径，如 'concepts/rag.md' 或 'entities/choreo.md'。
                   可先用 kb_grep 找到页面路径。

    Returns:
        页面完整 Markdown 内容，或未找到时的错误信息。
    """
    wiki_dir = _wiki_dir()
    target = (wiki_dir / page_path).resolve()

    if not str(target).startswith(str(wiki_dir.resolve())):
        return "Error: path traversal not allowed."
    if not target.exists():
        return f"Page not found: {page_path}. Use kb_grep to find available pages."

    return target.read_text(errors="replace")


@tool
async def kb_add_raw(filename: str, content: str) -> str:
    """将 Markdown 文件添加到 raw/ 目录，供下次编译时处理。

    Args:
        filename: 以 .md 结尾的文件名，如 'meeting-notes-2026-06.md'。
        content: 要存储的 Markdown 内容。

    Returns:
        成功确认信息或错误信息。
    """
    if not filename.endswith(".md"):
        return "Error: filename must end in .md"

    raw_dir = _raw_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = (raw_dir / filename).resolve()

    if not str(target).startswith(str(raw_dir.resolve())):
        return "Error: path traversal not allowed."

    target.write_text(content, encoding="utf-8")
    return f"已保存到 raw/{filename}。请触发 /api/kb/ingest 将其编译到 wiki。"


# ── 以下工具专供 ingest/lint 无头 Agent 使用，直接操作 KB 目录（绕过沙箱）──

@tool
async def kb_list_raw() -> str:
    """列出 raw/ 目录中所有待编译的原始资料文件。

    Returns:
        每行一个文件名；若目录为空返回提示信息。
    """
    raw_dir = _raw_dir()
    files = sorted(f.name for f in raw_dir.iterdir() if f.is_file()) if raw_dir.exists() else []
    return "\n".join(files) if files else "raw/ 目录为空，暂无待编译文件。"


@tool
async def kb_read_raw(filename: str) -> str:
    """读取 raw/ 目录中的原始资料文件内容。

    Args:
        filename: raw/ 下的文件名，如 '考研备考计划.md'。

    Returns:
        文件完整内容，或错误信息。
    """
    raw_dir = _raw_dir()
    target = (raw_dir / filename).resolve()
    if not str(target).startswith(str(raw_dir.resolve())):
        return "Error: path traversal not allowed."
    if not target.exists():
        return f"文件不存在：raw/{filename}"
    return target.read_text(errors="replace")


@tool
async def kb_write_wiki(page_path: str, content: str) -> str:
    """在 wiki/ 目录下创建或覆盖一个页面。

    Args:
        page_path: 相对于 wiki/ 的路径，如 'concepts/rag.md' 或 'entities/choreo.md'。
                   必须位于 concepts/entities/sources/comparisons 子目录之一。
        content: 完整 Markdown 内容（含 YAML frontmatter）。

    Returns:
        成功确认信息或错误信息。
    """
    wiki_dir = _wiki_dir()
    target = (wiki_dir / page_path).resolve()
    if not str(target).startswith(str(wiki_dir.resolve())):
        return "Error: path traversal not allowed."
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入 wiki/{page_path}"


@tool
async def kb_read_log() -> str:
    """读取知识库编译日志（wiki/log.md）。

    Returns:
        日志完整内容。
    """
    log_path = _wiki_dir() / "log.md"
    if not log_path.exists():
        return ""
    return log_path.read_text(errors="replace")


@tool
async def kb_append_log(entry: str) -> str:
    """向知识库日志（wiki/log.md）追加一条记录。

    Args:
        entry: 要追加的日志行，如 '- 2026-06-04 14:00 ingest: processed 1 file, created 3 pages'。

    Returns:
        确认信息。
    """
    log_path = _wiki_dir() / "log.md"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry.rstrip() + "\n")
    return "日志已追加。"


@tool
async def kb_write_index(content: str) -> str:
    """覆盖写入知识库索引（wiki/index.md）。

    Args:
        content: 完整索引 Markdown 内容。

    Returns:
        确认信息。
    """
    index_path = _wiki_dir() / "index.md"
    index_path.write_text(content, encoding="utf-8")
    return "wiki/index.md 已更新。"
