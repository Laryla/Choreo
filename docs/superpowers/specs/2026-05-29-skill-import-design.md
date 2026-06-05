# Skill Import Feature Design

Date: 2026-05-29

## Summary

Replace the "新建技能" form-based creation flow with a file upload import flow. Users can upload a single `.md` skill file or a `.zip` package containing multiple skills. The flow is a three-step modal: upload → select (zip only) → resolve conflicts → done.

---

## User Flow

1. User clicks **导入技能** button in `CustomizeSkillsPage` toolbar.
2. A hidden `<input type="file" accept=".md,.zip">` opens the OS file picker.
3. On file select, the file is uploaded to `POST /api/skills/import/preview`.
4. Backend parses the file and returns a list of skills with conflict flags.
5. **If `.md`**: show a small category input (default `imported`), user confirms then goes to conflict check if needed.
6. **If `.zip`**: show **Step 2** — checklist of all skills in the zip. Skills that conflict are badged "已存在". User unchecks any they don't want.
7. If any selected skill conflicts, show **Step 3** — per-conflict choice (覆盖 / 跳过) with "全部覆盖" / "全部跳过" shortcuts.
8. User clicks **确认导入** → frontend calls `POST /api/skills/import/confirm` with session_id + selections + conflict decisions.
9. Backend writes skills to disk. Modal shows success summary.

---

## Backend

### New file: `backend/choreo/skills/importer.py`

Responsibilities:
- `parse_md(content: str) -> SkillCreate` — parse a single `.md` file with YAML frontmatter into a `SkillCreate`.
- `parse_zip(data: bytes) -> list[SkillCreate]` — unzip, find all `.md` files, parse each.
- In-memory session store: `dict[str, list[SkillCreate]]` keyed by UUID session_id. Sessions expire after 10 minutes (simple TTL via `asyncio` or timestamp check on access).

### New routes in `backend/choreo/gateway/routers/skills.py`

**`POST /api/skills/import/preview`**
- Accepts `multipart/form-data` with fields `file` (`.md` or `.zip`) and optional `category` (string, for single `.md` uploads; defaults to `imported`).
- Parses file via `importer.parse_md` or `importer.parse_zip`.
- Checks each parsed skill against `LocalSkillStore.get()` for conflicts.
- Stores result in session store, returns:
  ```json
  {
    "session_id": "uuid",
    "skills": [
      { "category": "design", "name": "frontend-design", "description": "...", "conflict": true },
      { "category": "animation", "name": "gsap-react", "description": "...", "conflict": false }
    ]
  }
  ```

**`POST /api/skills/import/confirm`**
- Body:
  ```json
  {
    "session_id": "uuid",
    "selections": ["design/frontend-design", "animation/gsap-react"],
    "conflict_decisions": {
      "design/frontend-design": "overwrite"
    }
  }
  ```
- Looks up session, filters to selected skills, applies decisions:
  - `overwrite` → call `store.update()`
  - `skip` (or not in selections) → no-op
  - no conflict → call `store.create()`
- Returns list of imported skill IDs.

### Category resolution

| Source | How category is determined |
|--------|---------------------------|
| Single `.md` | User inputs category in modal (default `imported`) |
| Zip with directories | From path inside zip: `design/frontend-design.md` → category `design` |
| Zip top-level `.md` | Falls back to `imported` |

---

## Frontend

### New component: `frontend/src/components/Skills/SkillImportModal.tsx`

State machine: `step: 'category' | 'select' | 'conflict' | 'done'`

Props:
```ts
{ onClose: () => void; onDone: () => void }
```

Internal state:
- `sessionId: string`
- `skills: PreviewSkill[]` (from preview response)
- `checked: Set<string>` (skill ids selected for import)
- `decisions: Record<string, 'overwrite' | 'skip'>` (conflict decisions)

Steps:
- **select** (zip only): checklist of skills, conflict badge on existing ones. "下一步" → if conflicts in checked set, go to `conflict`, else call confirm directly.
- **conflict**: per-conflict 覆盖/跳过 toggle, "全部覆盖" / "全部跳过" buttons. "确认导入" → call confirm.
- **done**: show count of imported skills. "关闭" → call `onDone`.

For single `.md` upload: show **category** step first (text input, default value `imported`). After user confirms category, call preview with the category override, then go to conflict step if needed, else confirm immediately.

### Changes to `frontend/src/api/skills.ts`

```ts
export interface PreviewSkill {
  category: string;
  name: string;
  description: string;
  conflict: boolean;
}

export interface ImportPreviewResponse {
  session_id: string;
  skills: PreviewSkill[];
}

export interface ImportConfirmBody {
  session_id: string;
  selections: string[];             // "category/name"
  conflict_decisions: Record<string, 'overwrite' | 'skip'>;
}

export const previewImport = (file: File): Promise<ImportPreviewResponse> => { ... }
export const confirmImport = (body: ImportConfirmBody): Promise<{ imported: string[] }> => { ... }
```

`previewImport` uses `FormData` with `file` field, sends to `POST /api/skills/import/preview`.

### Changes to `frontend/src/pages/CustomizeSkillsPage.tsx`

- Remove "新建技能" button and `SkillEditor` usage from the toolbar.
- Add hidden `<input type="file" accept=".md,.zip" ref={fileInputRef}>` with `onChange` that calls `previewImport`, then opens `SkillImportModal`.
- Add **导入技能** button that calls `fileInputRef.current?.click()`.

---

## Error Handling

- Invalid file type (not `.md` or `.zip`): backend returns 400, frontend shows inline error message.
- Zip contains no `.md` files: backend returns 400 with message "压缩包中未找到技能文件".
- Session expired or not found on confirm: backend returns 404, frontend shows error and asks user to re-upload.
- Malformed `.md` (missing frontmatter): skip the file, include it in a `skipped` list returned from preview.

---

## Out of Scope

- Exporting skills as zip.
- Installing skills from URL directly.
- Editing skills after import (use existing SkillEditor flow).
