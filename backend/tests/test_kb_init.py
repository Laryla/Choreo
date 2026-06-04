import pytest
from pathlib import Path
from choreo.kb.init import kb_init, DEFAULT_SCHEMA

def test_kb_init_creates_directories(tmp_path):
    kb_dir = str(tmp_path / "knowledge")
    kb_init(kb_dir)
    root = Path(kb_dir)
    assert (root / "raw").is_dir()
    assert (root / "wiki" / "concepts").is_dir()
    assert (root / "wiki" / "entities").is_dir()
    assert (root / "wiki" / "sources").is_dir()
    assert (root / "wiki" / "comparisons").is_dir()
    assert (root / "outputs").is_dir()

def test_kb_init_writes_schema(tmp_path):
    kb_dir = str(tmp_path / "knowledge")
    kb_init(kb_dir)
    schema = (Path(kb_dir) / "schema.md").read_text()
    assert "type: concept" in schema

def test_kb_init_writes_log_and_index(tmp_path):
    kb_dir = str(tmp_path / "knowledge")
    kb_init(kb_dir)
    assert (Path(kb_dir) / "wiki" / "log.md").exists()
    assert (Path(kb_dir) / "wiki" / "index.md").exists()

def test_kb_init_is_idempotent(tmp_path):
    kb_dir = str(tmp_path / "knowledge")
    kb_init(kb_dir)
    kb_init(kb_dir)  # 不应抛出异常
    assert (Path(kb_dir) / "schema.md").exists()

def test_kb_init_does_not_overwrite_existing_schema(tmp_path):
    kb_dir = str(tmp_path / "knowledge")
    kb_init(kb_dir)
    custom = "# 我的自定义 Schema"
    (Path(kb_dir) / "schema.md").write_text(custom)
    kb_init(kb_dir)
    assert (Path(kb_dir) / "schema.md").read_text() == custom
