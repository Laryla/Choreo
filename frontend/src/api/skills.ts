const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const BASE = `${API}/api/skills`;

export interface Skill {
  id: string;
  category: string;
  name: string;
  description: string;
  version: string;
  author: string;
  tags: string[];
  content: string;
  source: "manual" | "auto" | "builtin" | "ai_review";
  state: "active" | "stale" | "archived";
  pinned: boolean;
  locked: boolean;
  use_count: number;
  view_count: number;
  patch_count: number;
  last_activity_at: number | null;
  last_reviewed_at: number | null;
  last_reviewed_by: string | null;
  arguments?: string;
}

export interface SkillCreate {
  category: string;
  name: string;
  description: string;
  version?: string;
  author?: string;
  tags?: string[];
  content?: string;
}

export interface SkillPatch {
  description?: string;
  version?: string;
  tags?: string[];
  content?: string;
  pinned?: boolean;
  state?: "active" | "archived";
  locked?: boolean;
}

export const getSkills = (q?: string, state?: string): Promise<Skill[]> => {
  const p = new URLSearchParams();
  if (q) p.set("q", q);
  if (state) p.set("state", state);
  const qs = p.toString();
  return fetch(`${BASE}/${qs ? "?" + qs : ""}`).then((r) => r.json());
};

export const createSkill = (body: SkillCreate): Promise<Skill> =>
  fetch(`${BASE}/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

export const patchSkill = (
  category: string,
  name: string,
  body: SkillPatch
): Promise<Skill> =>
  fetch(`${BASE}/${category}/${name}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const deleteSkill = (category: string, name: string): Promise<void> =>
  fetch(`${BASE}/${category}/${name}`, { method: "DELETE" }).then(() => undefined);

export const listSkillFiles = (category: string, name: string): Promise<string[]> =>
  fetch(`${BASE}/${category}/${name}/files`).then((r) => r.json()).then((d) => d.files ?? []);

export const readSkillFile = (
  category: string,
  name: string,
  filePath: string
): Promise<{ content: string; filename: string }> =>
  fetch(`${BASE}/${category}/${name}/files/${filePath}`).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

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
  selections: string[];
  conflict_decisions: Record<string, "overwrite" | "skip">;
}

export interface ImportConfirmResponse {
  imported: string[];
}

export const previewImport = (
  file: File,
  category?: string
): Promise<ImportPreviewResponse> => {
  const form = new FormData();
  form.append("file", file);
  if (category) form.append("category", category);
  return fetch(`${BASE}/import/preview`, { method: "POST", body: form }).then(
    (r) => {
      if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.detail ?? `${r.status}`)));
      return r.json();
    }
  );
};

export const confirmImport = (
  body: ImportConfirmBody
): Promise<ImportConfirmResponse> =>
  fetch(`${BASE}/import/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.detail ?? `${r.status}`)));
    return r.json();
  });

export interface ReviewLogEntry {
  thread_id: string;
  ts: number;
  updated: string[];
  created: string[];
}

export const getReviewLog = (limit = 1): Promise<ReviewLogEntry[]> =>
  fetch(`${BASE}/review_log?limit=${limit}`).then((r) => r.json());
