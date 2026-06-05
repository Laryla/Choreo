# 知识库页面重设计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将知识库页面从三 Tab 割裂布局重构为统一主页 + 过滤器 + 右侧滑入详情面板，双模式跟随项目主题。

**Architecture:** 后端 `list_wiki` 和 `list_raw` 接口新增字段（`summary`、`type`、`ref_count`、`compiled`），前端拆分为 4 个新组件（WikiCard、RawFileCard、DetailPanel、KnowledgeGrid），`KnowledgePage` 完全重写为组合这些组件的页面容器。

**Tech Stack:** FastAPI + Pydantic（后端）、React + TypeScript + Tailwind CSS + SWR + ReactMarkdown（前端）

---

## 文件变更地图

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/choreo/gateway/routers/knowledge.py` | 改 | 扩展 `WikiPageMeta`、`RawFile`，实现新字段计算 |
| `backend/tests/test_knowledge_router.py` | 改 | 补充新字段的测试 |
| `frontend/src/hooks/useKnowledge.ts` | 改 | 更新 TypeScript 类型定义 |
| `frontend/src/components/Knowledge/WikiCard.tsx` | 新建 | Wiki 条目卡片 |
| `frontend/src/components/Knowledge/RawFileCard.tsx` | 新建 | 原始资料卡片 |
| `frontend/src/components/Knowledge/DetailPanel.tsx` | 新建 | 右侧滑入详情面板 |
| `frontend/src/components/Knowledge/KnowledgeGrid.tsx` | 新建 | 卡片网格 + 分节标题 |
| `frontend/src/pages/KnowledgePage.tsx` | 重写 | 页面容器，组合所有组件 |

---

## Task 1: 后端——扩展 WikiPageMeta 和 RawFile

**Files:**
- Modify: `backend/choreo/gateway/routers/knowledge.py`
- Modify: `backend/tests/test_knowledge_router.py`

### 理解现有结构

`list_wiki()` 目前返回 `{"path", "name", "modified_at"}`，wiki 文件存放于 `wiki/{concepts,entities,sources,comparisons}/*.md`。

目录名 → `type` 映射：
- `concepts` → `"concept"`
- `entities` → `"entity"`
- `sources` → `"source-summary"`
- `comparisons` → `"comparison"`

`summary` = 去除 frontmatter（`---` 包裹的 YAML 块）后正文前 80 字符。

`ref_count` = 文件中 `[[...]]` 模式的出现次数。

`compiled`（RawFile）= 在 `wiki/` 下任意 `.md` 文件中出现 `[[{stem}]]` 即为已编译。

- [ ] **Step 1: 写失败测试——新字段存在**

在 `backend/tests/test_knowledge_router.py` 末尾追加：

```python
def test_list_wiki_has_new_fields(client, kb_dir):
    """list_wiki 应返回 summary / type / ref_count 字段。"""
    wiki_dir = Path(kb_dir) / "wiki" / "concepts"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "rag.md").write_text(
        "---\ntitle: RAG\n---\n\nRetrieval-Augmented Generation is a technique. [[向量数据库]]",
        encoding="utf-8",
    )
    res = client.get("/wiki/")
    assert res.status_code == 200
    pages = res.json()
    assert len(pages) == 1
    p = pages[0]
    assert p["type"] == "concept"
    assert "Retrieval-Augmented" in p["summary"]
    assert p["ref_count"] == 1


def test_list_raw_has_compiled_field(client, kb_dir):
    """list_raw 应返回 compiled 字段。"""
    import io
    # 上传一个原始文件
    client.post("/raw/", files={"file": ("paper.md", io.BytesIO(b"# Paper\nContent."), "text/markdown")})
    res = client.get("/raw/")
    assert res.status_code == 200
    files = res.json()
    assert len(files) == 1
    assert "compiled" in files[0]
    assert files[0]["compiled"] is False  # 尚未有 wiki 引用它


def test_raw_compiled_true_when_referenced(client, kb_dir):
    """wiki 页面 [[paper]] 引用时 raw/paper.md 应标记为 compiled=True。"""
    import io
    client.post("/raw/", files={"file": ("paper.md", io.BytesIO(b"# Paper\nContent."), "text/markdown")})
    # 手动创建引用该文件的 wiki 页面
    wiki_dir = Path(kb_dir) / "wiki" / "concepts"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    (wiki_dir / "summary.md").write_text("# Summary\n\n[[paper]]", encoding="utf-8")
    res = client.get("/raw/")
    assert res.status_code == 200
    assert res.json()[0]["compiled"] is True
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && uv run pytest tests/test_knowledge_router.py::test_list_wiki_has_new_fields tests/test_knowledge_router.py::test_list_raw_has_compiled_field tests/test_knowledge_router.py::test_raw_compiled_true_when_referenced -v
```

预期：3 个测试 FAIL（`KeyError: 'type'` 或 `AssertionError`）。

- [ ] **Step 3: 实现新字段计算函数**

在 `backend/choreo/gateway/routers/knowledge.py` 的 `_WIKI_CONTENT_DIRS` 定义后，添加：

```python
import re as _re

_DIR_TO_TYPE: dict[str, str] = {
    "concepts": "concept",
    "entities": "entity",
    "sources": "source-summary",
    "comparisons": "comparison",
}

_WIKILINK_RE = _re.compile(r"\[\[([^\]]+)\]\]")
_FRONTMATTER_RE = _re.compile(r"^---\s*\n.*?\n---\s*\n", _re.DOTALL)


def _parse_wiki_meta(md_file: Path, wiki_dir: Path) -> dict:
    """从 wiki markdown 文件提取 type / summary / ref_count。"""
    rel = md_file.relative_to(wiki_dir)
    dir_name = rel.parts[0]
    wiki_type = _DIR_TO_TYPE.get(dir_name, "concept")

    text = md_file.read_text(encoding="utf-8", errors="replace")
    body = _FRONTMATTER_RE.sub("", text, count=1).strip()
    summary = body[:80].replace("\n", " ")
    ref_count = len(_WIKILINK_RE.findall(text))

    return {"type": wiki_type, "summary": summary, "ref_count": ref_count}


def _compiled_stems(wiki_dir: Path) -> set[str]:
    """返回在 wiki 页面中被 [[...]] 引用过的词条名（小写 stem 集合）。"""
    stems: set[str] = set()
    if not wiki_dir.exists():
        return stems
    for md in wiki_dir.rglob("*.md"):
        for match in _WIKILINK_RE.finditer(md.read_text(encoding="utf-8", errors="replace")):
            stems.add(match.group(1).strip().lower())
    return stems
```

- [ ] **Step 4: 更新 `RawFile` 模型并修改 `list_raw`**

将现有 `RawFile` 模型替换为：

```python
class RawFile(BaseModel):
    name: str
    size: int
    modified_at: int
    compiled: bool
```

将 `list_raw` 函数替换为：

```python
@router.get("/raw/", response_model=list[RawFile])
async def list_raw():
    raw_dir = _kb_root() / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    wiki_dir = _kb_root() / "wiki"
    compiled = _compiled_stems(wiki_dir)
    return [
        RawFile(
            name=f.name,
            size=f.stat().st_size,
            modified_at=int(f.stat().st_mtime),
            compiled=Path(f.name).stem.lower() in compiled,
        )
        for f in sorted(raw_dir.iterdir())
        if f.is_file()
    ]
```

- [ ] **Step 5: 更新 `list_wiki` 函数**

将现有 `list_wiki` 函数完全替换为：

```python
@router.get("/wiki/")
async def list_wiki():
    wiki_dir = _kb_root() / "wiki"
    if not wiki_dir.exists():
        return []
    results = []
    for md in sorted(wiki_dir.rglob("*.md")):
        rel = md.relative_to(wiki_dir)
        if rel.parts[0] not in _WIKI_CONTENT_DIRS:
            continue
        meta = _parse_wiki_meta(md, wiki_dir)
        results.append({
            "path": str(rel),
            "name": md.stem,
            "modified_at": int(md.stat().st_mtime),
            **meta,
        })
    return results
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd backend && uv run pytest tests/test_knowledge_router.py -v
```

预期：全部 PASS。

- [ ] **Step 7: Commit**

```bash
git add backend/choreo/gateway/routers/knowledge.py backend/tests/test_knowledge_router.py
git commit -m "feat(kb): WikiPageMeta 新增 summary/type/ref_count，RawFile 新增 compiled"
```

---

## Task 2: 前端类型更新

**Files:**
- Modify: `frontend/src/hooks/useKnowledge.ts`

- [ ] **Step 1: 更新 `WikiPageMeta` 和 `RawFile` 接口**

打开 `frontend/src/hooks/useKnowledge.ts`，将：

```typescript
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
```

替换为：

```typescript
export interface RawFile {
  name: string;
  size: number;
  modified_at: number;
  compiled: boolean;
}

export interface WikiPageMeta {
  path: string;
  name: string;
  modified_at: number;
  summary: string;
  type: "concept" | "entity" | "source-summary" | "comparison";
  ref_count: number;
}
```

- [ ] **Step 2: Commit**

```bash
cd frontend && git add src/hooks/useKnowledge.ts
git commit -m "feat(kb): 更新前端 WikiPageMeta 和 RawFile 类型定义"
```

---

## Task 3: WikiCard 组件

**Files:**
- Create: `frontend/src/components/Knowledge/WikiCard.tsx`

类型标签颜色（`TYPE_BADGE` 映射）沿用现有 `TYPE_COLORS`，但改为 Tailwind 类名：
- `concept` → indigo
- `entity` → amber
- `source-summary` → emerald
- `comparison` → pink

- [ ] **Step 1: 创建组件文件**

新建 `frontend/src/components/Knowledge/WikiCard.tsx`：

```tsx
import type { WikiPageMeta } from "@/hooks/useKnowledge";

interface Props {
  page: WikiPageMeta;
  selected: boolean;
  onSelect: (page: WikiPageMeta) => void;
}

const TYPE_LABELS: Record<WikiPageMeta["type"], string> = {
  concept: "概念",
  entity: "实体",
  "source-summary": "来源摘要",
  comparison: "对比",
};

const TYPE_BADGE: Record<WikiPageMeta["type"], string> = {
  concept: "bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400",
  entity: "bg-amber-50 text-amber-600 dark:bg-amber-900/20 dark:text-amber-400",
  "source-summary": "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400",
  comparison: "bg-pink-50 text-pink-600 dark:bg-pink-900/20 dark:text-pink-400",
};

function relativeTime(ts: number): string {
  const diff = Math.floor((Date.now() / 1000 - ts) / 86400);
  if (diff === 0) return "今天";
  if (diff === 1) return "昨天";
  if (diff < 7) return `${diff} 天前`;
  if (diff < 30) return `${Math.floor(diff / 7)} 周前`;
  return `${Math.floor(diff / 30)} 个月前`;
}

export default function WikiCard({ page, selected, onSelect }: Props) {
  return (
    <button
      onClick={() => onSelect(page)}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-150 ${
        selected
          ? "border-[#6366f1] ring-1 ring-[#6366f1] bg-white dark:bg-[#1a1a2e]"
          : "border-[#e6e2da] dark:border-[#2d2d48] bg-white dark:bg-[#1e1e35] hover:border-[#bbb] dark:hover:border-[#4a4a75] hover:-translate-y-px"
      }`}
    >
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs px-2 py-0.5 rounded bg-indigo-50 text-indigo-600 dark:bg-indigo-900/20 dark:text-indigo-400 font-medium">
          📖 Wiki
        </span>
        <span className={`text-xs px-2 py-0.5 rounded font-medium ${TYPE_BADGE[page.type]}`}>
          {TYPE_LABELS[page.type]}
        </span>
      </div>
      <div className="text-sm font-semibold text-[#1a1a1a] dark:text-[#e2e8f0] mb-1.5 leading-snug">
        {page.name}
      </div>
      {page.summary && (
        <div className="text-xs text-[#888] dark:text-[#64748b] leading-relaxed line-clamp-2 mb-2.5">
          {page.summary}
        </div>
      )}
      <div className="flex items-center gap-1.5 text-[10px] text-[#aaa] dark:text-[#475569]">
        {page.ref_count > 0 && (
          <>
            <span>🔗 {page.ref_count} 个来源</span>
            <span>·</span>
          </>
        )}
        <span>{relativeTime(page.modified_at)}</span>
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Knowledge/WikiCard.tsx
git commit -m "feat(kb): 新建 WikiCard 组件"
```

---

## Task 4: RawFileCard 组件

**Files:**
- Create: `frontend/src/components/Knowledge/RawFileCard.tsx`

- [ ] **Step 1: 创建组件文件**

新建 `frontend/src/components/Knowledge/RawFileCard.tsx`：

```tsx
import type { RawFile } from "@/hooks/useKnowledge";

interface Props {
  file: RawFile;
  selected: boolean;
  onSelect: (file: RawFile) => void;
}

function extBadge(name: string): { label: string; cls: string } {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf") return { label: "PDF", cls: "bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400" };
  if (ext === "md") return { label: "MD", cls: "bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400" };
  if (ext === "docx") return { label: "DOCX", cls: "bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400" };
  return { label: ext.toUpperCase() || "FILE", cls: "bg-[#f5f2eb] text-[#555] dark:bg-[#2d2d48] dark:text-[#94a3b8]" };
}

export default function RawFileCard({ file, selected, onSelect }: Props) {
  const badge = extBadge(file.name);
  const sizeKB = (file.size / 1024).toFixed(1);

  return (
    <button
      onClick={() => onSelect(file)}
      className={`w-full text-left p-4 rounded-xl border transition-all duration-150 ${
        selected
          ? "border-[#6366f1] ring-1 ring-[#6366f1] bg-white dark:bg-[#1a1a2e]"
          : "border-[#e6e2da] dark:border-[#2d2d48] bg-white dark:bg-[#1e1e35] hover:border-[#bbb] dark:hover:border-[#4a4a75] hover:-translate-y-px"
      }`}
    >
      <span className={`text-xs px-2 py-0.5 rounded font-medium mb-2 inline-block ${badge.cls}`}>
        📄 {badge.label}
      </span>
      <div className="text-sm font-semibold text-[#1a1a1a] dark:text-[#e2e8f0] mb-2 leading-snug truncate">
        {file.name}
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-[#aaa] dark:text-[#475569]">
        <span
          className={`w-1.5 h-1.5 rounded-full inline-block ${
            file.compiled ? "bg-emerald-500" : "bg-amber-400"
          }`}
        />
        <span>{file.compiled ? "已编译" : "待编译"}</span>
        <span>·</span>
        <span>{sizeKB} KB</span>
      </div>
    </button>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Knowledge/RawFileCard.tsx
git commit -m "feat(kb): 新建 RawFileCard 组件"
```

---

## Task 5: DetailPanel 组件

**Files:**
- Create: `frontend/src/components/Knowledge/DetailPanel.tsx`

面板对 WikiPageMeta 调用 `useWikiPage(path)` 获取正文；对 RawFile 只展示元数据（正文不加载）。

引用来源列表：从 wiki 正文中提取 `[[...]]` 模式作为 source 标签展示。

- [ ] **Step 1: 创建组件文件**

新建 `frontend/src/components/Knowledge/DetailPanel.tsx`：

```tsx
import ReactMarkdown from "react-markdown";
import { useWikiPage } from "@/hooks/useKnowledge";
import type { WikiPageMeta, RawFile } from "@/hooks/useKnowledge";

type SelectedItem = { kind: "wiki"; data: WikiPageMeta } | { kind: "raw"; data: RawFile };

interface Props {
  item: SelectedItem | null;
  onClose: () => void;
}

function extractSources(content: string): string[] {
  const matches = [...content.matchAll(/\[\[([^\]]+)\]\]/g)];
  return [...new Set(matches.map((m) => m[1].trim()))];
}

function WikiDetail({ page, onClose }: { page: WikiPageMeta; onClose: () => void }) {
  const { data } = useWikiPage(page.path);

  return (
    <>
      <div className="flex items-start justify-between gap-3 p-4 border-b border-[#e6e2da] dark:border-[#2d2d48]">
        <h2 className="text-base font-bold text-[#1a1a1a] dark:text-[#e2e8f0] leading-snug">{page.name}</h2>
        <button
          onClick={onClose}
          className="w-6 h-6 flex-shrink-0 flex items-center justify-center rounded text-[#aaa] hover:text-[#555] dark:hover:text-[#e2e8f0] bg-[#f5f2eb] dark:bg-[#22223a] border border-[#e6e2da] dark:border-[#3a3a55] text-xs"
        >
          ✕
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {data ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <ReactMarkdown>{data.content}</ReactMarkdown>
          </div>
        ) : (
          <div className="text-sm text-[#aaa] dark:text-[#475569]">加载中…</div>
        )}
      </div>
      {data && extractSources(data.content).length > 0 && (
        <div className="p-4 border-t border-[#e6e2da] dark:border-[#2d2d48]">
          <p className="text-[10px] uppercase tracking-wide text-[#aaa] dark:text-[#475569] font-semibold mb-2">
            引用来源
          </p>
          <div className="flex flex-col gap-1">
            {extractSources(data.content).map((src) => (
              <div
                key={src}
                className="text-xs px-2 py-1.5 rounded-md bg-[#f5f2eb] dark:bg-[#1e1e35] border border-[#e6e2da] dark:border-[#2d2d48] text-[#666] dark:text-[#94a3b8]"
              >
                🔗 {src}
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

function RawDetail({ file, onClose }: { file: RawFile; onClose: () => void }) {
  const sizeKB = (file.size / 1024).toFixed(1);
  return (
    <>
      <div className="flex items-start justify-between gap-3 p-4 border-b border-[#e6e2da] dark:border-[#2d2d48]">
        <h2 className="text-base font-bold text-[#1a1a1a] dark:text-[#e2e8f0] leading-snug break-all">{file.name}</h2>
        <button
          onClick={onClose}
          className="w-6 h-6 flex-shrink-0 flex items-center justify-center rounded text-[#aaa] hover:text-[#555] dark:hover:text-[#e2e8f0] bg-[#f5f2eb] dark:bg-[#22223a] border border-[#e6e2da] dark:border-[#3a3a55] text-xs"
        >
          ✕
        </button>
      </div>
      <div className="p-4 flex flex-col gap-3">
        <div className="flex items-center gap-2 text-sm text-[#555] dark:text-[#94a3b8]">
          <span
            className={`w-2 h-2 rounded-full ${file.compiled ? "bg-emerald-500" : "bg-amber-400"}`}
          />
          <span>{file.compiled ? "已编译入知识图谱" : "尚未编译"}</span>
        </div>
        <div className="text-sm text-[#888] dark:text-[#64748b]">大小：{sizeKB} KB</div>
        {!file.compiled && (
          <p className="text-xs text-[#aaa] dark:text-[#475569]">
            点击「触发编译」将此文件编译进知识库。
          </p>
        )}
      </div>
    </>
  );
}

export default function DetailPanel({ item, onClose }: Props) {
  const visible = item !== null;

  return (
    <div
      className={`flex flex-col w-96 flex-shrink-0 bg-white dark:bg-[#16162a] border-l border-[#e6e2da] dark:border-[#2d2d48] overflow-hidden transition-all duration-200 ${
        visible ? "translate-x-0" : "translate-x-full w-0"
      }`}
    >
      {item?.kind === "wiki" && <WikiDetail page={item.data} onClose={onClose} />}
      {item?.kind === "raw" && <RawDetail file={item.data} onClose={onClose} />}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Knowledge/DetailPanel.tsx
git commit -m "feat(kb): 新建 DetailPanel 右侧滑入面板组件"
```

---

## Task 6: KnowledgeGrid 组件

**Files:**
- Create: `frontend/src/components/Knowledge/KnowledgeGrid.tsx`

- [ ] **Step 1: 创建组件文件**

新建 `frontend/src/components/Knowledge/KnowledgeGrid.tsx`：

```tsx
import WikiCard from "./WikiCard";
import RawFileCard from "./RawFileCard";
import type { WikiPageMeta, RawFile } from "@/hooks/useKnowledge";

type SelectedItem = { kind: "wiki"; data: WikiPageMeta } | { kind: "raw"; data: RawFile };

interface Props {
  wikiPages: WikiPageMeta[];
  rawFiles: RawFile[];
  filter: "all" | "wiki" | "raw";
  query: string;
  selectedItem: SelectedItem | null;
  onSelectWiki: (page: WikiPageMeta) => void;
  onSelectRaw: (file: RawFile) => void;
}

export default function KnowledgeGrid({
  wikiPages,
  rawFiles,
  filter,
  query,
  selectedItem,
  onSelectWiki,
  onSelectRaw,
}: Props) {
  const q = query.toLowerCase();

  const filteredWiki = wikiPages.filter(
    (p) =>
      (filter === "all" || filter === "wiki") &&
      (!q || p.name.toLowerCase().includes(q) || p.summary?.toLowerCase().includes(q))
  );

  const filteredRaw = rawFiles.filter(
    (f) =>
      (filter === "all" || filter === "raw") &&
      (!q || f.name.toLowerCase().includes(q))
  );

  const isEmpty = filteredWiki.length === 0 && filteredRaw.length === 0;

  if (isEmpty) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[#aaa] dark:text-[#475569]">
        {q ? `未找到与「${query}」相关的内容` : "暂无内容"}
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      {filteredWiki.length > 0 && (
        <>
          <p className="text-xs font-semibold uppercase tracking-wide text-[#aaa] dark:text-[#475569] mb-3 pb-2 border-b border-[#e6e2da] dark:border-[#2d2d48]">
            Wiki 条目 · {filteredWiki.length} 篇
          </p>
          <div className="grid gap-3 mb-6" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {filteredWiki.map((p) => (
              <WikiCard
                key={p.path}
                page={p}
                selected={selectedItem?.kind === "wiki" && selectedItem.data.path === p.path}
                onSelect={onSelectWiki}
              />
            ))}
          </div>
        </>
      )}
      {filteredRaw.length > 0 && (
        <>
          <p className="text-xs font-semibold uppercase tracking-wide text-[#aaa] dark:text-[#475569] mb-3 pb-2 border-b border-[#e6e2da] dark:border-[#2d2d48]">
            原始资料 · {filteredRaw.length} 份
          </p>
          <div className="grid gap-3" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {filteredRaw.map((f) => (
              <RawFileCard
                key={f.name}
                file={f}
                selected={selectedItem?.kind === "raw" && selectedItem.data.name === f.name}
                onSelect={onSelectRaw}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/Knowledge/KnowledgeGrid.tsx
git commit -m "feat(kb): 新建 KnowledgeGrid 卡片网格组件"
```

---

## Task 7: 重写 KnowledgePage

**Files:**
- Modify: `frontend/src/pages/KnowledgePage.tsx`

这一步完全替换现有文件，组合所有新组件。保留现有 `GraphView` 组件逻辑（直接内联复制，不抽取）。

- [ ] **Step 1: 完整重写 KnowledgePage.tsx**

用以下内容**完全替换** `frontend/src/pages/KnowledgePage.tsx`：

```tsx
import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import Topbar from "@/components/Topbar/Topbar";
import KnowledgeGrid from "@/components/Knowledge/KnowledgeGrid";
import DetailPanel from "@/components/Knowledge/DetailPanel";
import {
  useRawFiles, useWikiList, useKBGraph,
  uploadRaw, triggerIngest, triggerLint, triggerProfileUpdate, triggerPullSources,
  type WikiPageMeta, type RawFile,
} from "@/hooks/useKnowledge";

type Filter = "all" | "wiki" | "raw" | "graph";
type SelectedItem = { kind: "wiki"; data: WikiPageMeta } | { kind: "raw"; data: RawFile };

// ---- GraphView（内联复用，无需改动）----
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
    const width = svgRef.current.clientWidth || 800;
    const height = svgRef.current.clientHeight || 600;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const labelToId = new Map(data.nodes.map((n) => [n.label, n.id]));
    const nodeIds = new Set(data.nodes.map((n) => n.id));
    const resolvedEdges = data.edges
      .map((e) => ({ source: e.source, target: labelToId.get(e.target) ?? e.target }))
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));

    const container = svg.append("g");
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", (event) => container.attr("transform", event.transform));
    svg.call(zoom).on("dblclick.zoom", null);

    const simulation = d3.forceSimulation(data.nodes as any)
      .force("link", d3.forceLink(resolvedEdges).id((d: any) => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2));

    const link = container.append("g").selectAll("line")
      .data(resolvedEdges).join("line")
      .attr("stroke", "#ccc").attr("stroke-width", 1);

    const node = container.append("g").selectAll("circle")
      .data(data.nodes).join("circle")
      .attr("r", 8)
      .attr("fill", (d) => TYPE_COLORS[d.type] ?? "#999")
      .attr("cursor", "grab")
      .call((d3.drag<SVGCircleElement, any>()
        .on("start", (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
      ) as any);

    const label = container.append("g").selectAll("text")
      .data(data.nodes).join("text")
      .text((d) => d.label)
      .attr("font-size", 11).attr("fill", "#555").attr("pointer-events", "none").attr("dy", -12);

    const edgeId = (e: any) => ({
      s: typeof e.source === "object" ? e.source.id : e.source,
      t: typeof e.target === "object" ? e.target.id : e.target,
    });

    node
      .on("mouseenter", (_event, hovered: any) => {
        const connected = new Set<string>([hovered.id]);
        link.each((e: any) => { const { s, t } = edgeId(e); if (s === hovered.id || t === hovered.id) { connected.add(s); connected.add(t); } });
        link.attr("stroke", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? "#6366f1" : "#ccc"; })
            .attr("stroke-width", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? 2 : 1; })
            .attr("stroke-dasharray", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? null : "5,4"; })
            .attr("stroke-opacity", (e: any) => { const { s, t } = edgeId(e); return (s === hovered.id || t === hovered.id) ? 1 : 0.2; });
        node.attr("opacity", (n: any) => connected.has(n.id) ? 1 : 0.2);
        label.attr("opacity", (n: any) => connected.has(n.id) ? 1 : 0.2);
      })
      .on("mouseleave", () => {
        link.attr("stroke", "#ccc").attr("stroke-width", 1).attr("stroke-dasharray", null).attr("stroke-opacity", 1);
        node.attr("opacity", 1);
        label.attr("opacity", 1);
      });

    simulation.on("tick", () => {
      link.attr("x1", (d: any) => d.source.x).attr("y1", (d: any) => d.source.y)
          .attr("x2", (d: any) => d.target.x).attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });
    return () => { simulation.stop(); };
  }, [data]);

  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-[#aaa] dark:text-[#475569]">
        暂无知识图谱，请先上传资料并触发编译
      </div>
    );
  }
  return <svg ref={svgRef} className="w-full h-full" style={{ cursor: "move" }} />;
}
// ---- /GraphView ----

export default function KnowledgePage() {
  const { data: wikiPages = [] } = useWikiList();
  const { data: rawFiles = [] } = useRawFiles();

  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selectedItem, setSelectedItem] = useState<SelectedItem | null>(null);

  const [uploading, setUploading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [linting, setLinting] = useState(false);
  const [profiling, setProfiling] = useState(false);
  const [pulling, setPulling] = useState(false);

  const handleSelectWiki = (page: WikiPageMeta) => {
    setSelectedItem((prev) =>
      prev?.kind === "wiki" && prev.data.path === page.path ? null : { kind: "wiki", data: page }
    );
  };

  const handleSelectRaw = (file: RawFile) => {
    setSelectedItem((prev) =>
      prev?.kind === "raw" && prev.data.name === file.name ? null : { kind: "raw", data: file }
    );
  };

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

  const handleLint = async () => {
    setLinting(true);
    try { await triggerLint(); } finally { setTimeout(() => setLinting(false), 2000); }
  };

  const handlePullSources = async () => {
    setPulling(true);
    try { await triggerPullSources(); } finally { setTimeout(() => setPulling(false), 2000); }
  };

  const handleUpdateProfile = async () => {
    setProfiling(true);
    try { await triggerProfileUpdate(); } finally { setProfiling(false); }
  };

  const FILTERS: { id: Filter; label: string }[] = [
    { id: "all", label: "全部" },
    { id: "wiki", label: "Wiki" },
    { id: "raw", label: "原始资料" },
    { id: "graph", label: "图谱视图" },
  ];

  const btnBase =
    "text-xs px-3 py-1.5 rounded-lg border transition-colors disabled:opacity-50";
  const btnSecondary =
    `${btnBase} bg-[#ede9e0] dark:bg-[#22223a] border-[#d6d0c7] dark:border-[#3a3a55] text-[#555] dark:text-[#94a3b8] hover:bg-[#e0dbd0] dark:hover:bg-[#2d2d50]`;
  const btnPrimary =
    `${btnBase} bg-[#6366f1] border-[#6366f1] text-white hover:bg-[#5558e8]`;

  return (
    <div className="flex flex-col h-full bg-[#f5f2eb] dark:bg-[#141414]">
      <Topbar title="知识库" />

      {/* Header */}
      <div className="px-6 pt-4 pb-2">
        <h1 className="text-lg font-bold text-[#1a1a1a] dark:text-[#e2e8f0]">知识库</h1>
        <p className="text-xs text-[#888] dark:text-[#475569] mt-0.5">
          {wikiPages.length} 篇 Wiki · {rawFiles.length} 份原始资料
        </p>
      </div>

      {/* Search */}
      <div className="px-6 pb-3">
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#aaa] dark:text-[#475569] text-sm pointer-events-none">
            🔍
          </span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索概念、文章、原始资料…"
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-[#d6d0c7] dark:border-[#3a3a55] bg-white dark:bg-[#16162a] text-sm text-[#333] dark:text-[#e2e8f0] placeholder-[#aaa] dark:placeholder-[#475569] outline-none focus:border-[#6366f1] transition-colors"
          />
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-1.5 px-6 pb-3 border-b border-[#e6e2da] dark:border-[#2a2a2a]">
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => { setFilter(f.id); setSelectedItem(null); }}
              className={`text-xs px-3 py-1.5 rounded-full font-medium transition-colors ${
                filter === f.id
                  ? "bg-[#6366f1] text-white"
                  : "text-[#888] dark:text-[#64748b] hover:text-[#333] dark:hover:text-[#e2e8f0] hover:bg-[#e6e2da] dark:hover:bg-[#2d2d48]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-2">
          <label className={`${btnSecondary} cursor-pointer`}>
            {uploading ? "上传中…" : "📥 上传"}
            <input
              type="file"
              accept=".md,.txt,.pdf,.docx,.pptx,.xlsx,.html,.htm,.csv,.json,.xml"
              className="hidden"
              onChange={handleUpload}
            />
          </label>
          <button onClick={handlePullSources} disabled={pulling} className={btnSecondary}>
            {pulling ? "拉取中…" : "🔗 拉取外部源"}
          </button>
          <button onClick={handleLint} disabled={linting} className={btnSecondary}>
            {linting ? "检查中…" : "✓ Lint"}
          </button>
          <button onClick={handleUpdateProfile} disabled={profiling} className={btnSecondary}>
            {profiling ? "更新中…" : "👤 更新画���"}
          </button>
          <button onClick={handleIngest} disabled={ingesting} className={btnPrimary}>
            {ingesting ? "编译中…" : "⚡ 触发编译"}
          </button>
        </div>
      </div>

      {/* Main area */}
      <div className="flex flex-1 overflow-hidden">
        {filter === "graph" ? (
          <div className="flex-1 overflow-hidden">
            <GraphView />
          </div>
        ) : (
          <>
            <KnowledgeGrid
              wikiPages={wikiPages}
              rawFiles={rawFiles}
              filter={filter}
              query={query}
              selectedItem={selectedItem}
              onSelectWiki={handleSelectWiki}
              onSelectRaw={handleSelectRaw}
            />
            <DetailPanel
              item={selectedItem}
              onClose={() => setSelectedItem(null)}
            />
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 启动前端验证**

```bash
cd frontend && pnpm dev
```

浏览器打开 `http://localhost:5173/knowledge`，依次验证：
1. 页面正常渲染，标题 + 搜索框 + 过滤栏可见
2. 切换 light/dark 模式（Topbar 主题按钮），两个模式视觉均正常
3. 输入搜索词，卡片实时过滤
4. 点击 Wiki 过滤器，只显示 Wiki 卡片
5. 点击原始资料过滤器，只显示 RawFile 卡片
6. 点击图谱视图，D3 图谱替换主区域
7. 点击 Wiki 卡片，右侧详情面板滑入，再次点击同一卡片，面板关闭
8. 点击 ✕ 按钮，面板关闭
9. 五个操作按钮各点击一次，确认 loading 态和 API 调用正常

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/KnowledgePage.tsx
git commit -m "feat(kb): 重写 KnowledgePage——统一主页+过滤器+右侧详情面板"
```

---

## 自检结果

**Spec 覆盖确认：**
- PageHeader（标题 + 统计）✅ Task 7
- SearchBar（全宽、实时过滤）✅ Task 7
- FilterBar（4 个过滤 + 5 个操作按钮）✅ Task 7
- WikiCard（badge、标签、摘要、来源数）✅ Task 3
- RawFileCard（ext badge、编译状态点）✅ Task 4
- DetailPanel（右侧滑入、ReactMarkdown、引用来源）✅ Task 5
- KnowledgeGrid（分节、搜索过滤）✅ Task 6
- GraphView 复用无回归 ✅ Task 7（内联）
- 双模式主题跟随 ✅ 所有组件使用 `dark:` Tailwind 类
- 后端新字段 `summary / type / ref_count / compiled` ✅ Task 1

**类型一致性：**
- `SelectedItem` 类型在 `DetailPanel`、`KnowledgeGrid`、`KnowledgePage` 三处定义完全相同
- `WikiPageMeta.type` 字面量联合类型在 `useKnowledge.ts`（Task 2）和 `WikiCard.tsx`（Task 3）保持一致
