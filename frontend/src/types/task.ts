export interface Task {
  id: string;
  description: string;
  cron: string;
  script_path: string;
  status: "active" | "paused";
  last_run?: number;
  next_run?: number;
}

export interface TaskCreate {
  description: string;
  cron: string;
  script_path: string;
}
