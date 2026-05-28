import type { Task, TaskCreate } from "@/types/task";

const BASE = "/api/tasks";

export const getTasks = (): Promise<Task[]> =>
  fetch(BASE).then((r) => r.json());

export const createTask = (body: TaskCreate): Promise<Task> =>
  fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const patchTask = (id: string, body: { status: "active" | "paused" }): Promise<Task> =>
  fetch(`${BASE}/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const deleteTask = (id: string): Promise<void> =>
  fetch(`${BASE}/${id}`, { method: "DELETE" }).then(() => undefined);
