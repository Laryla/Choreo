from pathlib import Path

from langchain_core.tools import tool

from choreo.config import settings


def _wiki_dir() -> Path:
    return Path(settings.KNOWLEDGE_BASE_DIR) / "wiki"


def _raw_dir() -> Path:
    return Path(settings.KNOWLEDGE_BASE_DIR) / "raw"


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
