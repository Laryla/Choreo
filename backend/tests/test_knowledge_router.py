import pytest
import io
from pathlib import Path
from fastapi.testclient import TestClient
from fastapi import FastAPI
from choreo.gateway.routers.knowledge import router
from choreo.kb.init import kb_init


@pytest.fixture
def kb_dir(tmp_path, monkeypatch):
    d = str(tmp_path / "kb")
    kb_init(d)
    monkeypatch.setattr("choreo.config.settings.KNOWLEDGE_BASE_DIR", d)
    monkeypatch.setattr("choreo.gateway.routers.knowledge._kb_root", lambda: Path(d))
    return d


@pytest.fixture
def app(kb_dir):
    a = FastAPI()
    a.include_router(router)
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_raw_empty(client):
    res = client.get("/raw/")
    assert res.status_code == 200
    assert res.json() == []


def test_upload_and_list_raw(client, kb_dir):
    content = b"# \xe6\xb5\x8b\xe8\xaf\x95\n\nHello."
    res = client.post("/raw/", files={"file": ("test.md", io.BytesIO(content), "text/markdown")})
    assert res.status_code == 201
    assert res.json()["filename"] == "test.md"

    res = client.get("/raw/")
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "test.md"


def test_upload_rejects_non_md(client):
    res = client.post("/raw/", files={"file": ("evil.sh", io.BytesIO(b"rm -rf /"), "text/plain")})
    assert res.status_code == 400


def test_list_wiki_empty(client):
    res = client.get("/wiki/")
    assert res.status_code == 200
    assert res.json() == []


def test_read_wiki_page(client, kb_dir):
    wiki_dir = Path(kb_dir) / "wiki" / "concepts"
    (wiki_dir / "rag.md").write_text("---\ntitle: RAG\n---\n一些内容。")
    res = client.get("/wiki/concepts/rag.md")
    assert res.status_code == 200
    assert "一些内容" in res.json()["content"]


def test_read_wiki_404(client):
    res = client.get("/wiki/concepts/nonexistent.md")
    assert res.status_code == 404


def test_get_graph_empty(client):
    res = client.get("/graph")
    assert res.status_code == 200
    assert res.json() == {"nodes": [], "edges": []}


def test_get_log(client):
    res = client.get("/log")
    assert res.status_code == 200
    assert "content" in res.json()
