// frontend/src/lib/api.ts
import { authStore } from "@/store/authStore";

const API = (import.meta as any).env?.VITE_API_URL ?? "http://localhost:8000";

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = authStore.getRefreshToken();
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${API}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const { access_token } = await res.json();
    authStore.setTokens(access_token, refreshToken);
    return access_token;
  } catch {
    return null;
  }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = authStore.getAccessToken();
  const headers = {
    ...init.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  let res = await fetch(`${API}${path}`, { ...init, headers });

  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      res = await fetch(`${API}${path}`, {
        ...init,
        headers: { ...headers, Authorization: `Bearer ${newToken}` },
      });
    } else {
      authStore.clearTokens();
      window.location.href = "/login";
    }
  }

  return res;
}
