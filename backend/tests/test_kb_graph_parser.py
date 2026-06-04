import pytest
from pathlib import Path
from choreo.kb.graph_parser import parse_graph

def _make_wiki(tmp_path: Path, pages: dict[str, str]) -> str:
    kb_dir = str(tmp_path / "kb")
    wiki_dir = tmp_path / "kb" / "wiki"
    wiki_dir.mkdir(parents=True)
    for filename, content in pages.items():
        target = wiki_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return kb_dir

def test_parse_graph_empty(tmp_path):
    kb_dir = _make_wiki(tmp_path, {})
    result = parse_graph(kb_dir)
    assert result == {"nodes": [], "edges": []}

def test_parse_graph_single_page_no_links(tmp_path):
    kb_dir = _make_wiki(tmp_path, {
        "concepts/rag.md": "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n检索增强生成。"
    })
    result = parse_graph(kb_dir)
    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["label"] == "RAG"
    assert result["nodes"][0]["type"] == "concept"
    assert result["edges"] == []

def test_parse_graph_extracts_wikilinks(tmp_path):
    kb_dir = _make_wiki(tmp_path, {
        "concepts/rag.md": "---\ntitle: RAG\ntype: concept\nconfidence: high\n---\n参见 [[LlamaIndex]] 和 [[pgvector]]。",
        "entities/llamaindex.md": "---\ntitle: LlamaIndex\ntype: entity\nconfidence: high\n---\n一个框架。",
    })
    result = parse_graph(kb_dir)
    assert len(result["nodes"]) == 2
    sources = [e["source"] for e in result["edges"]]
    targets = [e["target"] for e in result["edges"]]
    assert "concepts/rag.md" in sources
    assert "LlamaIndex" in targets
    assert "pgvector" in targets

def test_parse_graph_uses_filename_stem_when_no_frontmatter(tmp_path):
    kb_dir = _make_wiki(tmp_path, {
        "concepts/no-frontmatter.md": "关于 [[某个概念]] 的纯文本。"
    })
    result = parse_graph(kb_dir)
    assert result["nodes"][0]["label"] == "no-frontmatter"
    assert result["nodes"][0]["type"] == "concept"
