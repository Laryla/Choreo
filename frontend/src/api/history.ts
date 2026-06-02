const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8009";

export interface HistoryItem {
  thread_id: string;
  title: string;
  status: string;
  created_at: number;
}

export interface HistoryPage {
  total: number;
  page: number;
  size: number;
  items: HistoryItem[];
}

export const getHistory = (page = 1, size = 20): Promise<HistoryPage> =>
  fetch(`${API}/api/history?page=${page}&size=${size}`).then((r) => r.json());
