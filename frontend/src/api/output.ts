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
