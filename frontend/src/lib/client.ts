import { Client } from "@langchain/langgraph-sdk";

export const client = new Client({
  apiUrl: (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000",
});
