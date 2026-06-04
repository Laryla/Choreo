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
