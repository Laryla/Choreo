# LLM Wiki 个人知识库 实施计划

> **面向自动化执行器：** 必须使用子 Agent 驱动开发（推荐）或执行计划技能逐任务实施。步骤使用复选框 (`- [ ]`) 语法跟踪进度。

**目标：** 为 Choreo 添加个人 LLM Wiki 知识库——原始资料由无头 Agent 编译成结构化、相互链接的 wiki 页面，配备知识图谱可视化和 Agent 搜索工具。

**架构：** 三层文件系统（`raw/` → 无头 Agent 编译器 → `wiki/`）。Agent 使用现有文件工具（read_file/write_file/list_dir/grep）将原始资料编译成带 `[[wikilinks]]` 的 wiki 页面。知识图谱通过解析所有 wiki 页面的 wikilinks 动态生成。对外暴露三个 Agent 工具：`kb_grep`、`kb_read`、`kb_add_raw`。无需新数据库，无需向量嵌入。

**技术栈：** Python/FastAPI（已有）、pytest（已有）、React/TypeScript/SWR（已有）、`react-markdown`（已安装）、`d3`（新增，用于图谱）。

---

## 文件清单

**新建：**
- `backend/choreo/kb/__init__.py`
- `backend/choreo/kb/init.py` — 目录初始化、默认 schema.md
- `backend/choreo/kb/graph_parser.py` — 解析 [[wikilinks]] → 节点/边
- `backend/choreo/kb/compiler_prompt.py` — INGEST_PROMPT、LINT_PROMPT
- `backend/choreo/agents/tools/kb_tools.py` — kb_grep、kb_read、kb_add_raw
- `backend/choreo/gateway/routers/knowledge.py` — 8 个 API 端点
- `backend/tests/test_kb_init.py`
- `backend/tests/test_kb_graph_parser.py`
- `backend/tests/test_kb_tools.py`
- `frontend/src/hooks/useKnowledge.ts`
- `frontend/src/pages/KnowledgePage.tsx`

**修改：**
- `backend/choreo/config.py` — 添加 KNOWLEDGE_BASE_DIR
- `backend/choreo/agents/choreo_agent.py` — 注册 3 个 KB 工具
- `backend/choreo/agents/prompt.py` — 添加工具说明
- `backend/choreo/gateway/app.py` — kb_init + include_router
- `backend/choreo/scheduler/runner.py` — 自动归档工作流结果
- `frontend/src/App.tsx` — 添加 /knowledge 路由
- `frontend/src/components/Sidebar/Sidebar.tsx` — 添加导航项

---

## 任务一：配置 + 知识库目录初始化

**涉及文件：**
- 修改：`backend/choreo/config.py`
- 新建：`backend/choreo/kb/__init__.py`
- 新建：`backend/choreo/kb/init.py`
- 测试：`backend/tests/test_kb_init.py`

- [ ] **编写失败测试**

```python
# backend/tests/test_kb_init.py
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
```

- [ ] **运行测试验证失败**

```bash
cd backend && uv run pytest tests/test_kb_init.py -v
```
预期：ImportError 或 ModuleNotFoundError

- [ ] **在 config.py 中添加 KNOWLEDGE_BASE_DIR**

在 `backend/choreo/config.py` 的 `CHOREO_SANDBOX_WORKDIR` 之后添加：
```python
# 知识库
KNOWLEDGE_BASE_DIR: str = "./knowledge"
```

- [ ] **新建 `backend/choreo/kb/__init__.py`**（空文件）

- [ ] **新建 `backend/choreo/kb/init.py`**

```python
from pathlib import Path
import textwrap

DEFAULT_SCHEMA = textwrap.dedent("""\
    # 知识库 Schema

    ## 页面规范
    每个 wiki 页面必须包含 YAML frontmatter：
    ```yaml
    ---
    title: 页面标题
    type: concept | entity | source-summary | comparison
    sources:
      - raw/filename.md
    related:
      - "[[相关概念]]"
    created: YYYY-MM-DD
    updated: YYYY-MM-DD
    confidence: high | medium | low
    ---
    ```
    文件名：使用 kebab-case 英文，例如 `project-choreo.md`。
    内部链接：使用 `[[页面标题]]` 格式。

    ## 页面类型
    - **concept**：理论、技术、方法（如"RAG 检索"）
    - **entity**：人物、项目、组织（如"Choreo 项目"）
    - **source-summary**：一个原始资料文件的摘要
    - **comparison**：多个概念/方案的对比分析

    ## 编译规则
    1. 永远不要修改 raw/ 中的文件
    2. 每次操作都追加到 wiki/log.md
    3. 遇到矛盾时，在 frontmatter 中添加 `contradictedBy: ["[[其他页面]]"]`——不要自动合并
    """)


def kb_init(kb_dir: str) -> None:
    root = Path(kb_dir)
    for subdir in [
        "raw",
        "wiki/concepts",
        "wiki/entities",
        "wiki/sources",
        "wiki/comparisons",
        "outputs",
    ]:
        (root / subdir).mkdir(parents=True, exist_ok=True)

    schema_path = root / "schema.md"
    if not schema_path.exists():
        schema_path.write_text(DEFAULT_SCHEMA, encoding="utf-8")

    log_path = root / "wiki" / "log.md"
    if not log_path.exists():
        log_path.write_text("# 知识库日志\n\n", encoding="utf-8")

    index_path = root / "wiki" / "index.md"
    if not index_path.exists():
        index_path.write_text("# 知识库索引\n\n", encoding="utf-8")
```

- [ ] **运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_kb_init.py -v
```
预期：5 个测试通过

- [ ] **提交**

```bash
git add backend/choreo/config.py backend/choreo/kb/ backend/tests/test_kb_init.py
git commit -m "feat(kb): 添加 KB 配置和目录初始化"
```

---

## 任务二：图谱解析器

**涉及文件：**
- 新建：`backend/choreo/kb/graph_parser.py`
- 测试：`backend/tests/test_kb_graph_parser.py`

- [ ] **编写失败测试**

```python
# backend/tests/test_kb_graph_parser.py
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
```

- [ ] **运行测试验证失败**

```bash
cd backend && uv run pytest tests/test_kb_graph_parser.py -v
```

- [ ] **新建 `backend/choreo/kb/graph_parser.py`**

```python
import re
from pathlib import Path

import yaml


def _extract_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        return yaml.safe_load(content[3:end]) or {}
    except Exception:
        return {}


def _infer_type_from_path(path: str) -> str:
    if "concepts/" in path:
        return "concept"
    if "entities/" in path:
        return "entity"
    if "sources/" in path:
        return "source-summary"
    if "comparisons/" in path:
        return "comparison"
    return "concept"


def parse_graph(kb_dir: str) -> dict:
    wiki_dir = Path(kb_dir) / "wiki"
    if not wiki_dir.exists():
        return {"nodes": [], "edges": []}

    nodes: list[dict] = []
    edges: list[dict] = []

    for md_file in sorted(wiki_dir.rglob("*.md")):
        content = md_file.read_text(errors="replace")
        fm = _extract_frontmatter(content)
        page_id = str(md_file.relative_to(wiki_dir))
        title = fm.get("title") or md_file.stem
        page_type = fm.get("type") or _infer_type_from_path(page_id)

        nodes.append({"id": page_id, "label": title, "type": page_type})

        for link in re.findall(r"\[\[([^\]]+)\]\]", content):
            edges.append({"source": page_id, "target": link})

    return {"nodes": nodes, "edges": edges}
```

- [ ] **运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_kb_graph_parser.py -v
```
预期：4 个测试通过

- [ ] **提交**

```bash
git add backend/choreo/kb/graph_parser.py backend/tests/test_kb_graph_parser.py
git commit -m "feat(kb): 添加 wiki 图谱解析器（支持 [[wikilinks]]）"
```

---

## 任务三：KB Agent 工具

**涉及文件：**
- 新建：`backend/choreo/agents/tools/kb_tools.py`
- 测试：`backend/tests/test_kb_tools.py`
- 修改：`backend/choreo/agents/choreo_agent.py`
- 修改：`backend/choreo/agents/prompt.py`

- [ ] **编写失败测试**

```python
# backend/tests/test_kb_tools.py
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
```

- [ ] **运行测试验证失败**

```bash
cd backend && uv run pytest tests/test_kb_tools.py -v
```

- [ ] **新建 `backend/choreo/agents/tools/kb_tools.py`**

```python
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
```

- [ ] **运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_kb_tools.py -v
```
预期：6 个测试通过

- [ ] **在 `choreo_agent.py` 中注册工具**

文件顶部添加导入：
```python
from choreo.agents.tools.kb_tools import kb_grep, kb_read, kb_add_raw
```

在 `create_choreo_agent` 的 `if headless:` 块中，将以下内容加入 `_allowed` 集合：
```python
"kb_grep", "kb_read", "kb_add_raw",
```

将以下内容加入 `_all` 列表：
```python
kb_grep, kb_read, kb_add_raw,
```

在非无头模式的 `return create_agent(...)` 中，将以下内容加入 `tools=[...]`：
```python
kb_grep, kb_read, kb_add_raw,
```

- [ ] **更新 `agents/prompt.py`**

在 `build_system_prompt()` 的工具列表末尾追加：
```python
"- kb_grep：搜索个人知识库（执行任务前先查相关背景）\n"
"- kb_read：读取知识库中的特定 wiki 页面\n"
"- kb_add_raw：向知识库添加原始资料（供下次编译时处理）\n"
```

- [ ] **提交**

```bash
git add backend/choreo/agents/tools/kb_tools.py backend/tests/test_kb_tools.py \
        backend/choreo/agents/choreo_agent.py backend/choreo/agents/prompt.py
git commit -m "feat(kb): 添加 kb_grep/kb_read/kb_add_raw Agent 工具"
```

---

## 任务四：编译器 Prompt

**涉及文件：**
- 新建：`backend/choreo/kb/compiler_prompt.py`

无需测试（字符串模板）。

- [ ] **新建 `backend/choreo/kb/compiler_prompt.py`**

```python
INGEST_PROMPT = """\
你是知识库管理员。执行增量编译，将 raw/ 里的新资料编译成结构化 wiki 页面。

**阶段一 — 识别新文件**
1. 用 list_dir 列出 raw/ 目录
2. 用 read_file 读取 wiki/log.md，找到上次编译的时间戳
3. 对比文件修改时间（或 log.md 中记录的已处理文件名），确定新增/变更的文件

**阶段二 — 编译**
对每个新文件：
4. 用 read_file 读取内容
5. 提取所有涉及的概念（concept）和实体（entity/project/person）
6. 在 wiki/concepts/ 或 wiki/entities/ 创建或更新对应页面
   - 每个页面必须包含完整 YAML frontmatter（参考 {kb_dir}/schema.md）
   - 正文使用 [[wiki-link]] 链接到相关概念
7. 在 wiki/sources/ 为该原始文件创建摘要页（type: source-summary）

**阶段三 — 收尾**
8. 追加本次操作记录到 wiki/log.md：
   `- YYYY-MM-DD HH:MM ingest: 处理了 N 个文件，创建/更新了 M 个页面`
9. 更新 wiki/index.md（分 Concepts / Entities / Sources 三节，列出所有页面及其 title）

知识库根目录：{kb_dir}
格式规范：{kb_dir}/schema.md
"""

LINT_PROMPT = """\
扫描知识库健康状态并生成报告。

检查以下问题：
1. **缺失页面**：被 [[引用]] 但尚未创建的页面（在所有 wiki 页中搜索 [[links]]，对比实际文件）
2. **孤儿页面**：没有任何入链的页面（存在但从未被 [[引用]]）
3. **矛盾页面**：frontmatter 中 contradictedBy 字段非空的页面
4. **格式问题**：缺少必要 frontmatter 字段（title/type/confidence）的页面

将报告写入 outputs/lint-{date}.md：
```
# Lint 报告 {date}
## 缺失页面 (N)
- [[页面名]] — 被引用于：page1.md, page2.md
## 孤儿页面 (N)
- path/to/page.md
## 矛盾页面 (N)
- path/to/page.md: contradictedBy [[其他页面]]
## 格式问题 (N)
- path/to/page.md: 缺少字段：confidence
```

知识库根目录：{kb_dir}
"""
```

- [ ] **提交**

```bash
git add backend/choreo/kb/compiler_prompt.py
git commit -m "feat(kb): 添加 ingest 和 lint 编译器 Prompt"
```

---

## 任务五：API 路由

**涉及文件：**
- 新建：`backend/choreo/gateway/routers/knowledge.py`
- 测试：`backend/tests/test_knowledge_router.py`

- [ ] **编写失败测试**

```python
# backend/tests/test_knowledge_router.py
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
    content = b"# 测试\n\nHello."
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
```

- [ ] **运行测试验证失败**

```bash
cd backend && uv run pytest tests/test_knowledge_router.py -v
```

- [ ] **新建 `backend/choreo/gateway/routers/knowledge.py`**

```python
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile, File
from pydantic import BaseModel

from choreo.config import settings
from choreo.kb.graph_parser import parse_graph

router = APIRouter()


def _kb_root() -> Path:
    return Path(settings.KNOWLEDGE_BASE_DIR)


class RawFile(BaseModel):
    name: str
    size: int
    modified_at: int


@router.get("/raw/", response_model=list[RawFile])
async def list_raw():
    raw_dir = _kb_root() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    return [
        RawFile(name=f.name, size=f.stat().st_size, modified_at=int(f.stat().st_mtime))
        for f in sorted(raw_dir.iterdir())
        if f.is_file()
    ]


@router.post("/raw/", status_code=201)
async def upload_raw(file: UploadFile = File(...)):
    if not file.filename or not file.filename.endswith(".md"):
        raise HTTPException(400, "只支持 .md 文件")
    raw_dir = _kb_root() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = (raw_dir / file.filename).resolve()
    if not str(target).startswith(str(raw_dir.resolve())):
        raise HTTPException(400, "非法文件名")
    target.write_bytes(await file.read())
    return {"filename": file.filename}


@router.get("/wiki/")
async def list_wiki():
    wiki_dir = _kb_root() / "wiki"
    if not wiki_dir.exists():
        return []
    return [
        {"path": str(md.relative_to(wiki_dir)), "name": md.stem, "modified_at": int(md.stat().st_mtime)}
        for md in sorted(wiki_dir.rglob("*.md"))
    ]


@router.get("/wiki/{page_path:path}")
async def read_wiki(page_path: str):
    wiki_dir = _kb_root() / "wiki"
    target = (wiki_dir / page_path).resolve()
    if not str(target).startswith(str(wiki_dir.resolve())):
        raise HTTPException(400, "非法路径")
    if not target.exists():
        raise HTTPException(404, "页面不存在")
    return {"path": page_path, "content": target.read_text(errors="replace")}


@router.get("/graph")
async def get_graph():
    return parse_graph(settings.KNOWLEDGE_BASE_DIR)


@router.get("/log")
async def get_log():
    log_path = _kb_root() / "wiki" / "log.md"
    if not log_path.exists():
        return {"content": ""}
    return {"content": log_path.read_text(errors="replace")}


async def _run_ingest() -> None:
    from langchain_core.messages import HumanMessage
    from choreo.agents.choreo_agent import create_choreo_agent
    from choreo.kb.compiler_prompt import INGEST_PROMPT
    kb_dir = str(_kb_root().resolve())
    agent = create_choreo_agent(headless=True)
    await agent.ainvoke({"messages": [HumanMessage(content=INGEST_PROMPT.format(kb_dir=kb_dir))]})


async def _run_lint() -> None:
    from langchain_core.messages import HumanMessage
    from choreo.agents.choreo_agent import create_choreo_agent
    from choreo.kb.compiler_prompt import LINT_PROMPT
    kb_dir = str(_kb_root().resolve())
    date = datetime.now().strftime("%Y-%m-%d")
    agent = create_choreo_agent(headless=True)
    await agent.ainvoke({"messages": [HumanMessage(content=LINT_PROMPT.format(kb_dir=kb_dir, date=date))]})


@router.post("/ingest")
async def trigger_ingest(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_ingest)
    return {"status": "started"}


@router.post("/lint")
async def trigger_lint(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_lint)
    return {"status": "started"}
```

- [ ] **运行测试验证通过**

```bash
cd backend && uv run pytest tests/test_knowledge_router.py -v
```
预期：8 个测试通过

- [ ] **提交**

```bash
git add backend/choreo/gateway/routers/knowledge.py backend/tests/test_knowledge_router.py
git commit -m "feat(kb): 添加知识库 API 路由"
```

---

## 任务六：应用集成

**涉及文件：**
- 修改：`backend/choreo/gateway/app.py`

- [ ] **在 `app.py` 中注册 KB 初始化和路由**

文件顶部添加导入：
```python
from choreo.kb.init import kb_init
from choreo.gateway.routers import knowledge as knowledge_router
```

在 `lifespan` 函数中，`await init_db()` 之后添加：
```python
    kb_init(settings.KNOWLEDGE_BASE_DIR)
```

在现有 `app.include_router(...)` 调用之后添加：
```python
app.include_router(
    knowledge_router.router,
    prefix="/api/kb",
    dependencies=[Depends(require_auth)],
)
```

- [ ] **启动后端验证路由**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload --port 8009
```
打开 `http://localhost:8009/docs`，确认 `/api/kb/raw/`、`/api/kb/wiki/`、`/api/kb/graph`、`/api/kb/ingest` 均已列出。

- [ ] **提交**

```bash
git add backend/choreo/gateway/app.py
git commit -m "feat(kb): 将 KB 初始化和路由集成到应用生命周期"
```

---

## 任务七：调度器自动归档

**涉及文件：**
- 修改：`backend/choreo/scheduler/runner.py`

- [ ] **在 `runner.py` 的 `TaskRunner.run()` 中添加自动归档**

在 `await update_run(run.id, status="success", output=output)` 行之后添加：

```python
        # 自动将工作流结果归档到 KB raw/
        if task.notify_config.get("archive_to_kb"):
            from pathlib import Path
            from datetime import datetime
            from choreo.config import settings
            raw_dir = Path(settings.KNOWLEDGE_BASE_DIR) / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"task-{task.id[:8]}-{date_str}.md"
            content = f"# 任务输出：{task.description}\n\n**日期：** {date_str}\n\n{output}"
            (raw_dir / filename).write_text(content, encoding="utf-8")
            logger.info("KB: 已将任务输出归档到 raw/%s", filename)
```

- [ ] **验证不破坏现有测试**

```bash
cd backend && uv run pytest tests/test_scheduler_runner.py -v
```
预期：全部通过

- [ ] **提交**

```bash
git add backend/choreo/scheduler/runner.py
git commit -m "feat(kb): 当 archive_to_kb=true 时自动归档任务输出到 KB raw/"
```

---

## 任务八：前端数据层

**涉及文件：**
- 新建：`frontend/src/hooks/useKnowledge.ts`

- [ ] **安装 d3**

```bash
cd frontend && pnpm add d3 @types/d3
```

- [ ] **新建 `frontend/src/hooks/useKnowledge.ts`**

```typescript
import useSWR, { mutate } from "swr";
import { apiFetch } from "@/lib/api";

const fetcher = (url: string) => apiFetch(url).then((r) => r.json());

export const KB_RAW_KEY = "/api/kb/raw/";
export const KB_WIKI_KEY = "/api/kb/wiki/";
export const KB_GRAPH_KEY = "/api/kb/graph";
export const KB_LOG_KEY = "/api/kb/log";

export interface RawFile {
  name: string;
  size: number;
  modified_at: number;
}

export interface WikiPageMeta {
  path: string;
  name: string;
  modified_at: number;
}

export interface KBGraphData {
  nodes: Array<{ id: string; label: string; type: string }>;
  edges: Array<{ source: string; target: string }>;
}

export function useRawFiles() {
  return useSWR<RawFile[]>(KB_RAW_KEY, fetcher);
}

export function useWikiList() {
  return useSWR<WikiPageMeta[]>(KB_WIKI_KEY, fetcher);
}

export function useKBGraph() {
  return useSWR<KBGraphData>(KB_GRAPH_KEY, fetcher);
}

export function useKBLog() {
  return useSWR<{ content: string }>(KB_LOG_KEY, fetcher, {
    refreshInterval: 3000,
  });
}

export function useWikiPage(path: string | null) {
  return useSWR<{ path: string; content: string }>(
    path ? `/api/kb/wiki/${path}` : null,
    fetcher
  );
}

export async function uploadRaw(file: File): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(KB_RAW_KEY, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  await mutate(KB_RAW_KEY);
}

export async function triggerIngest(): Promise<void> {
  await apiFetch("/api/kb/ingest", { method: "POST" });
  await mutate(KB_LOG_KEY);
}

export async function triggerLint(): Promise<void> {
  await apiFetch("/api/kb/lint", { method: "POST" });
}
```

- [ ] **提交**

```bash
git add frontend/src/hooks/useKnowledge.ts frontend/package.json pnpm-lock.yaml
git commit -m "feat(kb): 添加前端数据 hooks 并安装 d3"
```

---

## 任务九：前端知识库页面 + 路由

**涉及文件：**
- 新建：`frontend/src/pages/KnowledgePage.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/components/Sidebar/Sidebar.tsx`

- [ ] **新建 `frontend/src/pages/KnowledgePage.tsx`**

```tsx
import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import ReactMarkdown from "react-markdown";
import Topbar from "@/components/Topbar/Topbar";
import {
  useRawFiles, useWikiList, useKBGraph, useKBLog, useWikiPage,
  uploadRaw, triggerIngest, triggerLint,
  type WikiPageMeta,
} from "@/hooks/useKnowledge";

type Tab = "wiki" | "graph" | "raw";

const TYPE_COLORS: Record<string, string> = {
  concept: "#6366f1",
  entity: "#f59e0b",
  "source-summary": "#10b981",
  comparison: "#ec4899",
};

function GraphView() {
  const { data } = useKBGraph();
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!data || !svgRef.current) return;
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const simulation = d3.forceSimulation(data.nodes as any)
      .force("link", d3.forceLink(data.edges).id((d: any) => d.label).distance(80))
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const link = svg.append("g").selectAll("line")
      .data(data.edges).join("line")
      .attr("stroke", "#ccc").attr("stroke-width", 1);

    const node = svg.append("g").selectAll("circle")
      .data(data.nodes).join("circle")
      .attr("r", 8)
      .attr("fill", (d) => TYPE_COLORS[d.type] ?? "#999")
      .attr("cursor", "pointer")
      .call(d3.drag<SVGCircleElement, any>()
        .on("start", (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    const label = svg.append("g").selectAll("text")
      .data(data.nodes).join("text")
      .text((d) => d.label)
      .attr("font-size", 11)
      .attr("fill", "#555")
      .attr("dy", -12);

    simulation.on("tick", () => {
      link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });

    return () => simulation.stop();
  }, [data]);

  if (!data || data.nodes.length === 0) {
    return <div className="flex items-center justify-center h-full text-sm text-[#aaa]">暂无知识图谱，请先上传资料并触发编译</div>;
  }
  return <svg ref={svgRef} className="w-full h-full" />;
}

function WikiView() {
  const { data: pages } = useWikiList();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const { data: page } = useWikiPage(selectedPath);

  return (
    <div className="flex h-full">
      <div className="w-56 flex-shrink-0 border-r border-[#e6e2da] dark:border-[#2a2a2a] overflow-y-auto p-3">
        {!pages || pages.length === 0
          ? <p className="text-xs text-[#aaa] px-2 py-4">暂无 wiki 页面</p>
          : pages.map((p: WikiPageMeta) => (
            <button
              key={p.path}
              onClick={() => setSelectedPath(p.path)}
              className={`w-full text-left text-xs px-2 py-1.5 rounded hover:bg-[#e6e2da] dark:hover:bg-[#1e1e1e] truncate ${selectedPath === p.path ? "bg-[#e6e2da] dark:bg-[#1e1e1e] font-medium" : "text-[#666]"}`}
            >
              {p.name}
            </button>
          ))
        }
      </div>
      <div className="flex-1 overflow-y-auto p-6">
        {page
          ? <div className="prose prose-sm dark:prose-invert max-w-none"><ReactMarkdown>{page.content}</ReactMarkdown></div>
          : <div className="flex items-center justify-center h-full text-sm text-[#aaa]">← 选择左侧页面查看内容</div>
        }
      </div>
    </div>
  );
}

function RawView() {
  const { data: files } = useRawFiles();
  const { data: log } = useKBLog();
  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try { await uploadRaw(file); } finally { setUploading(false); e.target.value = ""; }
  };

  const handleIngest = async () => {
    setIngesting(true);
    try { await triggerIngest(); } finally { setTimeout(() => setIngesting(false), 2000); }
  };

  return (
    <div className="flex flex-col h-full p-6 gap-4">
      <div className="flex items-center gap-3">
        <label className="text-xs px-3 py-1.5 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] cursor-pointer hover:opacity-80">
          {uploading ? "上传中…" : "上传 .md 文件"}
          <input type="file" accept=".md" className="hidden" onChange={handleUpload} />
        </label>
        <button
          onClick={handleIngest}
          disabled={ingesting}
          className="text-xs px-3 py-1.5 rounded-lg bg-[#6366f1] text-white hover:opacity-90 disabled:opacity-50"
        >
          {ingesting ? "编译中…" : "触发编译"}
        </button>
        <button onClick={triggerLint} className="text-xs px-3 py-1.5 rounded-lg bg-[#e6e2da] dark:bg-[#1e1e1e] border border-[#d6d0c7] dark:border-[#2a2a2a] hover:opacity-80">
          Lint 检查
        </button>
      </div>
      <div className="flex gap-4 flex-1 min-h-0">
        <div className="flex-1 overflow-y-auto">
          <p className="text-xs font-medium text-[#888] mb-2">原始资料（{files?.length ?? 0} 个）</p>
          {files?.map((f) => (
            <div key={f.name} className="text-xs py-1.5 border-b border-[#e6e2da] dark:border-[#2a2a2a] text-[#555] dark:text-[#888]">
              {f.name} <span className="text-[#aaa]">（{(f.size / 1024).toFixed(1)} KB）</span>
            </div>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto">
          <p className="text-xs font-medium text-[#888] mb-2">编译日志</p>
          <pre className="text-[10px] text-[#666] dark:text-[#555] whitespace-pre-wrap">{log?.content || "暂无日志"}</pre>
        </div>
      </div>
    </div>
  );
}

export default function KnowledgePage() {
  const [tab, setTab] = useState<Tab>("wiki");

  const tabs: { id: Tab; label: string }[] = [
    { id: "wiki", label: "Wiki 浏览" },
    { id: "graph", label: "知识图谱" },
    { id: "raw", label: "原始资料" },
  ];

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="知识库" />
      <div className="flex gap-0 border-b border-[#e6e2da] dark:border-[#2a2a2a] px-6">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`text-xs px-4 py-2.5 border-b-2 transition-colors ${tab === t.id ? "border-[#6366f1] text-[#6366f1]" : "border-transparent text-[#888] hover:text-[#555]"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-hidden">
        {tab === "wiki" && <WikiView />}
        {tab === "graph" && <GraphView />}
        {tab === "raw" && <RawView />}
      </div>
    </div>
  );
}
```

- [ ] **在 `App.tsx` 中添加 `/knowledge` 路由**

添加导入：
```tsx
import KnowledgePage from "./pages/KnowledgePage";
```

在受保护路由的 `<Routes>` 中，现有路由之后添加：
```tsx
<Route path="/knowledge" element={<KnowledgePage />} />
```

- [ ] **在 `Sidebar.tsx` 中添加导航项**

在 `NAV_ITEMS` 数组中（"历史记录"条目之后）添加：
```tsx
{
  to: "/knowledge",
  label: "知识库",
  icon: (
    <svg className="w-4 h-4 opacity-60 flex-shrink-0" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 2h7l3 3v9H3V2z" /><path d="M10 2v3h3" /><line x1="5" y1="7" x2="11" y2="7" /><line x1="5" y1="10" x2="9" y2="10" />
    </svg>
  ),
},
```

- [ ] **启动前端验证**

```bash
cd frontend && pnpm dev
```
打开 `http://localhost:5173/knowledge`，验证三个 Tab 正常渲染，侧边栏显示"知识库"入口。

- [ ] **提交**

```bash
git add frontend/src/pages/KnowledgePage.tsx \
        frontend/src/App.tsx \
        frontend/src/components/Sidebar/Sidebar.tsx
git commit -m "feat(kb): 添加知识库页面（Wiki/图谱/原始资料三标签）及路由"
```

---

## 自检清单

**功能覆盖：**
- ✅ raw/ 目录 + 上传 API（任务五、八、九）
- ✅ wiki/ 编译页面（任务四的 Prompt、任务六的集成）
- ✅ 默认 schema.md（任务一）
- ✅ kb_grep / kb_read / kb_add_raw Agent 工具（任务三）
- ✅ [[wikilinks]] 知识图谱（任务二、五）
- ✅ D3 图谱可视化（任务九）
- ✅ Ingest + Lint 触发（任务五、九）
- ✅ 工作流自动归档（任务七）
- ✅ 侧边栏导航 + 路由（任务九）
- ✅ log.md 日志展示（任务八、九）

**类型一致性：**
- `parse_graph(kb_dir: str)` → `{"nodes": [...], "edges": [...]}` 在路由和前端中一致使用
- `kb_grep/kb_read/kb_add_raw` 均为 async 工具；测试使用 `asyncio.run(tool.ainvoke({...}))`
- `KBGraphData.nodes[i].label` 与 D3 模拟的 id 访问器 `(d: any) => d.label` 一致
- `RawFile` schema 与路由响应模型一致

**无占位符：** 所有步骤均包含完整可执行代码。
