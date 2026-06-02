import { apiFetch } from "@/lib/api";
import type { Task, TaskCreate, TaskRun } from "@/types/task";

const BASE = "/api/tasks";

export const getTasks = (): Promise<Task[]> =>
  apiFetch(BASE).then((r) => r.json());

export const createTask = (body: TaskCreate): Promise<Task> =>
  apiFetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const patchTask = (id: string, body: { status: "active" | "paused" }): Promise<Task> =>
  apiFetch(`${BASE}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const deleteTask = (id: string): Promise<void> =>
  apiFetch(`${BASE}/${id}`, { method: "DELETE" }).then(() => undefined);

export const getTaskRuns = (taskId: string): Promise<TaskRun[]> =>
  apiFetch(`${BASE}/${taskId}/runs`).then((r) => r.json());

export const getTaskRun = (taskId: string, runId: string): Promise<TaskRun> =>
  apiFetch(`${BASE}/${taskId}/runs/${runId}`).then((r) => r.json());

export const triggerTaskRun = (taskId: string): Promise<TaskRun> =>
  apiFetch(`${BASE}/${taskId}/runs`, { method: "POST" }).then((r) => r.json());
