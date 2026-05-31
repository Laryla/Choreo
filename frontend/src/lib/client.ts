// frontend/src/lib/client.ts
import { Client } from "@langchain/langgraph-sdk";
import { authStore } from "@/store/authStore";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

export const getClient = () => {
  const token = authStore.getAccessToken();
  return new Client({
    apiUrl: API,
    defaultHeaders: token ? { Authorization: `Bearer ${token}` } : {},
  });
};

// Backwards-compatible proxy so existing `client.threads.xxx` calls still work
export const client = new Proxy({} as ReturnType<typeof getClient>, {
  get(_target, prop) {
    return (getClient() as any)[prop];
  },
});
