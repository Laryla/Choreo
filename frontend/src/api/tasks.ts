import { apiFetch } from "@/lib/api";
import type { Task, TaskCreate } from "@/types/task";

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
