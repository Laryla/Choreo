export interface Task {
  id: string;
  description: string;
  cron: string;
  prompt: string;
  script_path: string;
  notify_config: Record<string, unknown>;
  status: "active" | "paused";
  last_run?: number;
  next_run?: number;
}

export interface TaskCreate {
  description: string;
  cron: string;
  prompt: string;
  script_path?: string;
  notify_config?: Record<string, unknown>;
}

export interface TaskRun {
  id: string;
  task_id: string;
  status: "pending" | "running" | "success" | "failed";
  started_at: number;
  finished_at?: number;
  output: string;
  error?: string;
}
