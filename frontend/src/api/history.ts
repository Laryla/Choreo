export const getHistory = (page = 1, size = 20, taskId?: string) => {
  const p = new URLSearchParams({ page: String(page), size: String(size) });
  if (taskId) p.set("task_id", taskId);
  return fetch(`/api/history?${p}`).then((r) => r.json());
};

export const getOutput = (runId: string): Promise<string> =>
  fetch(`/api/history/${runId}/output`).then((r) => r.text());
