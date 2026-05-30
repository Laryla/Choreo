const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";
const BASE = `${API}/api/mcp`;

export interface ToolConfig {
  approval: "auto" | "confirm" | "deny";
  enabled: boolean;
}

export interface McpServer {
  name: string;
  transport: "stdio" | "sse" | "http";
  command: string | null;
  args: string[];
  url: string | null;
  env: Record<string, string>;
  tools_config: Record<string, ToolConfig>;
  enabled: boolean;
  created_at: number;
}

export interface McpServerCreate {
  name: string;
  transport: "stdio" | "sse" | "http";
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  tools_config?: Record<string, ToolConfig>;
  enabled?: boolean;
}

export interface McpServerPatch {
  transport?: "stdio" | "sse" | "http";
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
  tools_config?: Record<string, ToolConfig>;
  enabled?: boolean;
}

export const listServers = (): Promise<McpServer[]> =>
  fetch(`${BASE}/`).then((r) => r.json());

export const createServer = (body: McpServerCreate): Promise<McpServer> =>
  fetch(`${BASE}/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => {
    if (!r.ok) return r.json().then((e) => Promise.reject(new Error(e.detail ?? `${r.status}`)));
    return r.json();
  });

export const patchServer = (name: string, body: McpServerPatch): Promise<McpServer> =>
  fetch(`${BASE}/${name}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

export const deleteServer = (name: string): Promise<void> =>
  fetch(`${BASE}/${name}`, { method: "DELETE" }).then(() => undefined);

export const reloadServers = (): Promise<{ status: string; servers: string[] }> =>
  fetch(`${BASE}/reload`, { method: "POST" }).then((r) => {
    if (!r.ok) throw new Error(`${r.status}`);
    return r.json();
  });

export const getDiscoveredTools = (): Promise<
  Record<string, Array<{ name: string; description: string }>>
> => fetch(`${BASE}/tools`).then((r) => r.json());
