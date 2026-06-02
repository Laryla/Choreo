# Output Directory File Preview Design

## Goal

Redesign `CustomizeOutputPage` with a left-right split layout and in-panel file preview (text, markdown, images) — no page navigation required.

## Architecture

Single page component split into two panels. Left panel manages file browsing state; right panel renders selected file content fetched from existing `/api/output/file` endpoint (text) or a new `/api/output/raw` endpoint (binary/images). No new routing.

## Tech Stack

- React + TypeScript (existing)
- `react-markdown` (already installed, v10)
- Tailwind CSS (existing)
- SWR (existing, for file content fetch)
- FastAPI `FileResponse` for binary endpoint

---

## Components

### `CustomizeOutputPage` (modified)

Top-level layout: `flex h-full`. Owns all state:

```
selectedThread: string
subdir: string
breadcrumb: string[]
selectedFile: OutputFile | null
```

Renders `<FileBrowser>` (left, 40%) and `<FilePreview>` (right, 60%) side by side.

### `FileBrowser` (new, extracted)

Props: `{ selectedThread, subdir, breadcrumb, selectedFile, onThreadChange, onEnterDir, onGoTo, onGoRoot, onSelectFile, onDownload }`

Contains:
- Thread selector dropdown (existing)
- Breadcrumb navigation (existing)
- File list table — clicking a file calls `onSelectFile`, directories call `onEnterDir`
- Download button per file row (right-aligned)
- Highlighted row for `selectedFile`

### `FilePreview` (new)

Props: `{ file: OutputFile | null, filePath: string, threadId: string }`

`filePath` is computed by the parent: `subdir ? "${subdir}/${file.name}" : file.name`.

Text content is fetched via SWR keyed on `["preview", filePath, threadId]`, calling `/api/output/file`. Images skip the fetch and use `getRawUrl()` directly as `<img src>`.

- When `file` is null: empty state ("← 点击左侧文件预览")
- Top bar: filename + download button
- Content area (scrollable):
  - **Image** (`png`, `jpg`, `jpeg`, `gif`, `svg`, `webp`): `<img src="/api/output/raw?path=...&thread_id=...">` centered
  - **Markdown** (`md`, `mdx`): fetch text → render with `<ReactMarkdown>`
  - **Other**: fetch text → `<pre>` with line numbers, monospace font

File type detection: by extension via a `getFileType(name)` utility returning `"image" | "markdown" | "text"`.

---

## Backend Changes

### New endpoint: `GET /api/output/raw`

Added to `backend/choreo/gateway/routers/output.py`.

```python
@router.get("/output/raw")
async def get_raw_file(path: str, thread_id: str = ""):
    # Same path resolution as get_file()
    # Returns FileResponse with detected media type
    return FileResponse(target, media_type=_guess_media_type(target.suffix))
```

`_guess_media_type` maps `.png → image/png`, `.jpg → image/jpeg`, `.svg → image/svg+xml`, etc.

Register in `gateway/app.py` (already registered via `router`).

---

## API

| Endpoint | Used for |
|----------|---------|
| `GET /api/output/?thread_id=&subdir=` | List files (existing) |
| `GET /api/output/file?path=&thread_id=` | Fetch text content (existing) |
| `GET /api/output/raw?path=&thread_id=` | Fetch binary/image (new) |

`getFileUrl` in `frontend/src/api/output.ts` unchanged (used for download via `window.open`).

Add `getRawUrl(path, threadId)` helper:
```ts
export const getRawUrl = (path: string, threadId = ""): string => {
  const params = new URLSearchParams({ path });
  if (threadId) params.set("thread_id", threadId);
  return `/api/output/raw?${params.toString()}`;
};
```

---

## Layout Spec

```
┌─────────────────────────────────────────────────────────┐
│ CustomizeOutputPage (flex h-full)                       │
│  ┌──────────────────────┐  ┌────────────────────────┐   │
│  │ FileBrowser (40%)    │  │ FilePreview (60%)      │   │
│  │                      │  │                        │   │
│  │ [Thread selector]    │  │ filename.py  ↓ 下载    │   │
│  │ output/ > charts/    │  │ ─────────────────────  │   │
│  │ ─────────────────    │  │ 1 │ import pandas...   │   │
│  │ 📁 charts/           │  │ 2 │ data = pd.read...  │   │
│  │ 📄 report.md         │  │ 3 │ data.plot()        │   │
│  │ 📄 data.csv          │  │                        │   │
│  │ ▶ 📄 output.py ←sel  │  │                        │   │
│  └──────────────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

Left panel has a right border separator. Right panel is scrollable independently. Both panels are full height.

---

## Error Handling

- File fetch 404: show "文件不存在" in preview area
- File fetch error: show error message, offer retry
- Empty directory: show existing empty state
- Image load error: show broken image fallback text

---

## Files Changed

| File | Action |
|------|--------|
| `frontend/src/pages/CustomizeOutputPage.tsx` | Rewrite — split layout, owns state |
| `frontend/src/components/Output/FileBrowser.tsx` | New component |
| `frontend/src/components/Output/FilePreview.tsx` | New component |
| `frontend/src/api/output.ts` | Add `getRawUrl()` |
| `backend/choreo/gateway/routers/output.py` | Add `GET /output/raw` endpoint |
