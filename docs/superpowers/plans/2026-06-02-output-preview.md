# Output Directory File Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the output directory page as a left-right split panel where clicking a file shows an inline preview (text, markdown-rendered, or image) on the right without page navigation.

**Architecture:** `CustomizeOutputPage` owns all state and renders `FileBrowser` (left 40%) + `FilePreview` (right 60%) side by side. A new backend endpoint `GET /api/output/raw` serves binary files (images) directly. Text/markdown files use the existing `/api/output/file` endpoint fetched via SWR in `FilePreview`.

**Tech Stack:** React + TypeScript, Tailwind CSS, SWR, react-markdown + remark-gfm (already installed), FastAPI `FileResponse`.

---

## File Map

| File | Action |
|------|--------|
| `frontend/src/api/output.ts` | Add `getRawUrl()` helper |
| `frontend/src/components/Output/FileBrowser.tsx` | New — left panel (list + breadcrumb + thread selector) |
| `frontend/src/components/Output/FilePreview.tsx` | New — right panel (renders text/md/image) |
| `frontend/src/pages/CustomizeOutputPage.tsx` | Rewrite — split layout, owns all state |
| `backend/choreo/gateway/routers/output.py` | Add `GET /output/raw` endpoint |

---

## Task 1: Add `getRawUrl` to output API and backend raw endpoint

**Files:**
- Modify: `frontend/src/api/output.ts`
- Modify: `backend/choreo/gateway/routers/output.py`

- [ ] **Step 1: Add `getRawUrl` to `frontend/src/api/output.ts`**

Replace the entire file with:

```typescript
import { apiFetch } from "@/lib/api";

export type OutputFile = {
  name: string;
  type: "file" | "dir";
  size: number | null;
};

export const listOutputFiles = (
  subdir = "",
  threadId = "",
): Promise<{ files: OutputFile[] }> => {
  const params = new URLSearchParams();
  if (subdir) params.set("subdir", subdir);
  if (threadId) params.set("thread_id", threadId);
  const qs = params.toString();
  return apiFetch(`/api/output/${qs ? `?${qs}` : ""}`).then((r) => r.json());
};

export const getFileUrl = (path: string, threadId = ""): string => {
  const params = new URLSearchParams({ path });
  if (threadId) params.set("thread_id", threadId);
  return `/api/output/file?${params.toString()}`;
};

export const getRawUrl = (path: string, threadId = ""): string => {
  const params = new URLSearchParams({ path });
  if (threadId) params.set("thread_id", threadId);
  return `/api/output/raw?${params.toString()}`;
};
```

- [ ] **Step 2: Add `GET /output/raw` to `backend/choreo/gateway/routers/output.py`**

Add these lines after the existing imports at the top:

```python
import mimetypes
from fastapi.responses import FileResponse
```

Then add this endpoint after `get_file()` at the bottom of the file:

```python
@router.get("/output/raw")
async def get_raw_file(path: str, thread_id: str = ""):
    safe = _safe_path(path)

    if thread_id:
        base = _thread_dir(thread_id)
    else:
        base = _get_output_root()

    target = (base / safe).resolve()

    if not str(target).startswith(str(base)):
        raise HTTPException(400, "Invalid path")

    if not target.exists() or not target.is_file():
        raise HTTPException(404, f"File not found: {path}")

    media_type, _ = mimetypes.guess_type(str(target))
    return FileResponse(str(target), media_type=media_type or "application/octet-stream")
```

- [ ] **Step 3: Restart backend and verify the endpoint works**

```bash
cd backend && uv run uvicorn choreo.gateway.app:app --reload --port 8009
```

In another terminal, test with a real image file if one exists, or create a test file:

```bash
# Create a test text file in any thread output dir
ls sandbox/output/
# Pick a thread_id from the listing, e.g. ee8d1c6a-...
curl "http://localhost:8009/api/output/raw?path=hello.txt&thread_id=ee8d1c6a-1b18-4110-a6ee-c4260344240a"
# Expected: file contents returned with text/plain content-type
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/output.ts backend/choreo/gateway/routers/output.py
git commit -m "feat(output): add getRawUrl helper and /output/raw binary endpoint"
```

---

## Task 2: Build `FileBrowser` component

**Files:**
- Create: `frontend/src/components/Output/FileBrowser.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Output/FileBrowser.tsx`:

```typescript
import { type OutputFile } from "@/api/output";

type Thread = { thread_id: string; status: string; title?: string };

interface FileBrowserProps {
  threads: Thread[];
  selectedThread: string;
  breadcrumb: string[];
  files: OutputFile[];
  isLoading: boolean;
  error: unknown;
  selectedFile: OutputFile | null;
  onThreadChange: (tid: string) => void;
  onGoRoot: () => void;
  onGoTo: (idx: number) => void;
  onEnterDir: (name: string) => void;
  onSelectFile: (file: OutputFile) => void;
  onDownload: (file: OutputFile) => void;
}

export default function FileBrowser({
  threads,
  selectedThread,
  breadcrumb,
  files,
  isLoading,
  error,
  selectedFile,
  onThreadChange,
  onGoRoot,
  onGoTo,
  onEnterDir,
  onSelectFile,
  onDownload,
}: FileBrowserProps) {
  const selectedTitle =
    threads.find((t) => t.thread_id === selectedThread)?.title ||
    (selectedThread ? selectedThread.slice(0, 8) + "…" : "");

  return (
    <div className="flex flex-col h-full border-r border-[#e8e4dc] dark:border-[#1a1a1a] overflow-hidden">
      {/* Thread selector */}
      <div className="flex-shrink-0 px-4 pt-4 pb-3 border-b border-[#e8e4dc] dark:border-[#1a1a1a]">
        <label className="block text-[10px] text-[#aaa] dark:text-[#555] font-medium uppercase tracking-wide mb-1.5">
          对话
        </label>
        <select
          value={selectedThread}
          onChange={(e) => onThreadChange(e.target.value)}
          className="w-full text-[12px] px-2.5 py-1.5 rounded-lg border border-[#e8e4dc] dark:border-[#1a1a1a] bg-white dark:bg-[#0d0d0d] text-[#333] dark:text-[#ccc] focus:outline-none focus:ring-1 focus:ring-[#c8b89a]"
        >
          <option value="">— 全部线程 —</option>
          {threads.map((t) => (
            <option key={t.thread_id} value={t.thread_id}>
              {t.title || t.thread_id.slice(0, 8) + "…"}
            </option>
          ))}
        </select>
      </div>

      {/* Breadcrumb */}
      <div className="flex-shrink-0 flex items-center gap-1 px-4 py-2 text-[11px] text-[#aaa] dark:text-[#555] font-mono border-b border-[#e8e4dc] dark:border-[#1a1a1a]">
        <button
          onClick={onGoRoot}
          className="hover:text-[#555] dark:hover:text-[#aaa] transition-colors"
        >
          {selectedTitle ? `${selectedTitle}/` : "output/"}
        </button>
        {breadcrumb.map((seg, i) => (
          <span key={i} className="flex items-center gap-1">
            <span>/</span>
            <button
              onClick={() => onGoTo(i)}
              className="hover:text-[#555] dark:hover:text-[#aaa] transition-colors"
            >
              {seg}
            </button>
          </span>
        ))}
      </div>

      {/* File list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && (
          <div className="px-4 py-8 text-center text-[12px] text-[#bbb] dark:text-[#333]">
            加载中…
          </div>
        )}
        {!isLoading && error && (
          <div className="px-4 py-8 text-center text-[12px] text-[#e07b54]">
            Sandbox 未运行，请先发送消息
          </div>
        )}
        {!isLoading && !error && files.length === 0 && (
          <div className="px-4 py-8 text-center text-[12px] text-[#bbb] dark:text-[#333]">
            output/ 目录为空
          </div>
        )}
        {!isLoading && !error && files.length > 0 && (
          <table className="w-full text-[12px]">
            <tbody>
              {files.map((f) => {
                const isSelected =
                  f.type === "file" && selectedFile?.name === f.name;
                return (
                  <tr
                    key={f.name}
                    className={`border-b border-[#f0ede6] dark:border-[#141414] last:border-0 transition-colors ${
                      isSelected
                        ? "bg-[#f0ede6] dark:bg-[#181818]"
                        : "hover:bg-[#faf8f5] dark:hover:bg-[#111]"
                    }`}
                  >
                    <td className="px-4 py-2.5">
                      {f.type === "dir" ? (
                        <button
                          onClick={() => onEnterDir(f.name)}
                          className="flex items-center gap-2 text-[#569cd6] hover:underline w-full text-left"
                        >
                          <svg
                            className="w-3.5 h-3.5 opacity-60 flex-shrink-0"
                            viewBox="0 0 16 16"
                            fill="currentColor"
                          >
                            <path d="M1.5 3.5A1.5 1.5 0 013 2h3.586a1.5 1.5 0 011.06.44L8.707 3.5H13A1.5 1.5 0 0114.5 5v7A1.5 1.5 0 0113 13.5H3A1.5 1.5 0 011.5 12V3.5z" />
                          </svg>
                          <span className="truncate">{f.name}/</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => onSelectFile(f)}
                          className="flex items-center gap-2 w-full text-left"
                        >
                          <svg
                            className="w-3.5 h-3.5 opacity-40 flex-shrink-0"
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.5"
                          >
                            <path d="M4 1.5h5.5L12.5 4.5V14.5H4V1.5z" />
                            <polyline points="9.5 1.5 9.5 4.5 12.5 4.5" />
                          </svg>
                          <span
                            className={`truncate ${
                              isSelected
                                ? "text-[#0f0f0f] dark:text-[#e8e8e8] font-medium"
                                : "text-[#333] dark:text-[#ccc]"
                            }`}
                          >
                            {f.name}
                          </span>
                        </button>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-right text-[#aaa] dark:text-[#555] font-mono text-[11px] whitespace-nowrap">
                      {f.size !== null ? formatSize(f.size) : ""}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {f.type === "file" && (
                        <button
                          onClick={() => onDownload(f)}
                          className="text-[11px] text-[#aaa] dark:text-[#444] hover:text-[#333] dark:hover:text-[#aaa] transition-colors"
                          title="下载"
                        >
                          ↓
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

Expected: No errors related to `FileBrowser.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Output/FileBrowser.tsx
git commit -m "feat(output): add FileBrowser component"
```

---

## Task 3: Build `FilePreview` component

**Files:**
- Create: `frontend/src/components/Output/FilePreview.tsx`

- [ ] **Step 1: Create the component**

Create `frontend/src/components/Output/FilePreview.tsx`:

```typescript
import useSWR from "swr";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getFileUrl, getRawUrl, type OutputFile } from "@/api/output";

type FileType = "image" | "markdown" | "text";

const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"]);
const MARKDOWN_EXTS = new Set(["md", "mdx", "markdown"]);

function getFileType(name: string): FileType {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (IMAGE_EXTS.has(ext)) return "image";
  if (MARKDOWN_EXTS.has(ext)) return "markdown";
  return "text";
}

async function fetchText(url: string): Promise<string> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.text();
}

interface FilePreviewProps {
  file: OutputFile | null;
  subdir: string;
  threadId: string;
  onDownload: () => void;
}

export default function FilePreview({
  file,
  subdir,
  threadId,
  onDownload,
}: FilePreviewProps) {
  if (!file) {
    return (
      <div className="flex items-center justify-center h-full text-[12px] text-[#bbb] dark:text-[#333]">
        ← 点击左侧文件预览
      </div>
    );
  }

  const filePath = subdir ? `${subdir}/${file.name}` : file.name;
  const fileType = getFileType(file.name);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-[#e8e4dc] dark:border-[#1a1a1a] bg-white dark:bg-[#0d0d0d]">
        <span className="text-[12px] font-mono text-[#555] dark:text-[#aaa] truncate">
          {file.name}
        </span>
        <button
          onClick={onDownload}
          className="flex-shrink-0 ml-3 text-[11px] text-[#888] dark:text-[#555] hover:text-[#333] dark:hover:text-[#aaa] transition-colors border border-[#e0dbd2] dark:border-[#222] rounded px-2 py-0.5"
        >
          ↓ 下载
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-auto bg-white dark:bg-[#0d0d0d]">
        {fileType === "image" ? (
          <ImagePreview
            src={getRawUrl(filePath, threadId)}
            name={file.name}
          />
        ) : (
          <TextPreview
            filePath={filePath}
            threadId={threadId}
            fileType={fileType}
          />
        )}
      </div>
    </div>
  );
}

function ImagePreview({ src, name }: { src: string; name: string }) {
  return (
    <div className="flex items-center justify-center p-6 min-h-full">
      <img
        src={src}
        alt={name}
        className="max-w-full max-h-[70vh] object-contain rounded shadow"
        onError={(e) => {
          (e.target as HTMLImageElement).style.display = "none";
          (e.target as HTMLImageElement).insertAdjacentText(
            "afterend",
            "图片加载失败"
          );
        }}
      />
    </div>
  );
}

function TextPreview({
  filePath,
  threadId,
  fileType,
}: {
  filePath: string;
  threadId: string;
  fileType: "markdown" | "text";
}) {
  const url = getFileUrl(filePath, threadId);
  const { data: content, isLoading, error } = useSWR(
    ["preview", filePath, threadId],
    () => fetchText(url),
  );

  if (isLoading) {
    return (
      <div className="px-6 py-8 text-center text-[12px] text-[#bbb] dark:text-[#333]">
        加载中…
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-6 py-8 text-center text-[12px] text-[#e07b54]">
        加载失败：{String(error?.message ?? error)}
      </div>
    );
  }

  if (fileType === "markdown") {
    return (
      <div className="px-6 py-5 prose prose-sm dark:prose-invert max-w-none text-[13px] leading-relaxed">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content ?? ""}
        </ReactMarkdown>
      </div>
    );
  }

  // Plain text / code
  const lines = (content ?? "").split("\n");
  return (
    <div className="px-0 py-0 overflow-x-auto">
      <table className="text-[11.5px] font-mono leading-[1.65] w-full border-collapse">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i} className="hover:bg-[#f8f6f2] dark:hover:bg-[#111]">
              <td className="pl-4 pr-3 text-right text-[#ccc] dark:text-[#333] select-none w-[3rem] border-r border-[#ece8e0] dark:border-[#1a1a1a]">
                {i + 1}
              </td>
              <td className="pl-4 pr-6 text-[#333] dark:text-[#ccc] whitespace-pre">
                {line}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

Expected: No errors related to `FilePreview.tsx`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Output/FilePreview.tsx
git commit -m "feat(output): add FilePreview component (text/markdown/image)"
```

---

## Task 4: Rewrite `CustomizeOutputPage` with split layout

**Files:**
- Modify: `frontend/src/pages/CustomizeOutputPage.tsx`

- [ ] **Step 1: Replace the file**

Replace the entire contents of `frontend/src/pages/CustomizeOutputPage.tsx`:

```typescript
import { useState } from "react";
import useSWR from "swr";
import { apiFetch } from "@/lib/api";
import { listOutputFiles, getFileUrl, type OutputFile } from "@/api/output";
import { THREADS_KEY } from "@/hooks/useChat";
import FileBrowser from "@/components/Output/FileBrowser";
import FilePreview from "@/components/Output/FilePreview";

type Thread = { thread_id: string; status: string; title?: string };

const threadFetcher = (url: string) => apiFetch(url).then((r) => r.json());

export default function CustomizeOutputPage() {
  const [selectedThread, setSelectedThread] = useState("");
  const [subdir, setSubdir] = useState("");
  const [breadcrumb, setBreadcrumb] = useState<string[]>([]);
  const [selectedFile, setSelectedFile] = useState<OutputFile | null>(null);

  const { data: threads = [] } = useSWR<Thread[]>(THREADS_KEY, threadFetcher, {
    revalidateOnFocus: true,
  });

  const { data, isLoading, error } = useSWR(
    ["output", selectedThread, subdir],
    () => listOutputFiles(subdir, selectedThread),
  );

  const handleThreadChange = (tid: string) => {
    setSelectedThread(tid);
    setSubdir("");
    setBreadcrumb([]);
    setSelectedFile(null);
  };

  const enterDir = (name: string) => {
    const next = subdir ? `${subdir}/${name}` : name;
    setSubdir(next);
    setBreadcrumb([...breadcrumb, name]);
    setSelectedFile(null);
  };

  const goTo = (idx: number) => {
    const crumbs = breadcrumb.slice(0, idx + 1);
    setBreadcrumb(crumbs);
    setSubdir(crumbs.join("/"));
    setSelectedFile(null);
  };

  const goRoot = () => {
    setBreadcrumb([]);
    setSubdir("");
    setSelectedFile(null);
  };

  const download = (file: OutputFile) => {
    const path = subdir ? `${subdir}/${file.name}` : file.name;
    window.open(getFileUrl(path, selectedThread));
  };

  const downloadSelected = () => {
    if (selectedFile) download(selectedFile);
  };

  return (
    <div className="flex h-full overflow-hidden bg-[#faf9f7] dark:bg-[#0a0a0a]">
      {/* Left: file browser (40%) */}
      <div className="w-[40%] min-w-[200px] max-w-[320px] flex-shrink-0 bg-white dark:bg-[#0d0d0d]">
        <FileBrowser
          threads={threads}
          selectedThread={selectedThread}
          breadcrumb={breadcrumb}
          files={data?.files ?? []}
          isLoading={isLoading}
          error={error}
          selectedFile={selectedFile}
          onThreadChange={handleThreadChange}
          onGoRoot={goRoot}
          onGoTo={goTo}
          onEnterDir={enterDir}
          onSelectFile={setSelectedFile}
          onDownload={download}
        />
      </div>

      {/* Right: preview (60%) */}
      <div className="flex-1 min-w-0 bg-white dark:bg-[#0d0d0d]">
        <FilePreview
          file={selectedFile}
          subdir={subdir}
          threadId={selectedThread}
          onDownload={downloadSelected}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && pnpm tsc --noEmit 2>&1 | head -30
```

Expected: No errors.

- [ ] **Step 3: Start dev server and test manually**

```bash
cd frontend && pnpm dev
```

Open http://localhost:5173/customize/output

Check:
1. Thread selector shows list of threads
2. Selecting a thread loads its files on the left
3. Clicking a `.txt` or `.py` file shows numbered line preview on the right
4. Clicking a `.md` file shows rendered markdown
5. Clicking an image file shows the image
6. Clicking a directory navigates into it, breadcrumb updates, selected file resets
7. Download button in preview top bar opens file download
8. Download `↓` button in file list row also works

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/CustomizeOutputPage.tsx
git commit -m "feat(output): split layout with FileBrowser + FilePreview panels"
```
