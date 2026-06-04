import pytest
from pathlib import Path


@pytest.fixture
def kb_dir(tmp_path):
    from choreo.kb.init import kb_init
    d = str(tmp_path / "kb")
    kb_init(d)
    return d


@pytest.fixture(autouse=True)
def patch_kb_dir(kb_dir, monkeypatch):
    monkeypatch.setattr("choreo.config.settings.KNOWLEDGE_BASE_DIR", kb_dir)


def test_kb_add_raw_creates_file(kb_dir):
    import asyncio
    from choreo.agents.tools.kb_tools import kb_add_raw
    result = asyncio.run(kb_add_raw.ainvoke({"filename": "notes.md", "content": "# 我的笔记\n\nHello world."}))
    assert "notes.md" in result
    assert (Path(kb_dir) / "raw" / "notes.md").read_text() == "# 我的笔记\n\nHello world."


def test_kb_add_raw_rejects_non_md(kb_dir):
    import asyncio
    from choreo.agents.tools.kb_tools import kb_add_raw
    result = asyncio.run(kb_add_raw.ainvoke({"filename": "evil.sh", "content": "rm -rf /"}))
    assert "Error" in result
    assert not (Path(kb_dir) / "raw" / "evil.sh").exists()


def test_kb_grep_finds_content(kb_dir):
    import asyncio
    from choreo.agents.tools.kb_tools import kb_grep
    wiki_dir = Path(kb_dir) / "wiki" / "concepts"
    (wiki_dir / "rag.md").write_text("---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n检索增强生成。")
    result = asyncio.run(kb_grep.ainvoke({"query": "检索增强"}))
    assert "rag.md" in result
    assert "检索增强" in result


def test_kb_grep_returns_no_results_message(kb_dir):
    import asyncio
    from choreo.agents.tools.kb_tools import kb_grep
    result = asyncio.run(kb_grep.ainvoke({"query": "xyzzy_not_found"}))
    assert "No results" in result


def test_kb_read_returns_content(kb_dir):
    import asyncio
    from choreo.agents.tools.kb_tools import kb_read
    wiki_dir = Path(kb_dir) / "wiki" / "entities"
    (wiki_dir / "choreo.md").write_text("# Choreo\n\n一个 Agent 平台。")
    result = asyncio.run(kb_read.ainvoke({"page_path": "entities/choreo.md"}))
    assert "Agent 平台" in result


def test_kb_read_rejects_path_traversal(kb_dir):
    import asyncio
    from choreo.agents.tools.kb_tools import kb_read
    result = asyncio.run(kb_read.ainvoke({"page_path": "../../etc/passwd"}))
    assert "Error" in result or "not found" in result.lower()
