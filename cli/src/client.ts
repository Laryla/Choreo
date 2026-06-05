export type DecisionType = 'approve' | 'reject' | 'edit';

export interface Decision {
  type: DecisionType;
  message?: string;
  edited_action?: { name: string; args: Record<string, unknown> };
}

export interface ApiClient {
  createThread(): Promise<string>;
  submitState(threadId: string, decisions: Decision[]): Promise<void>;
  acceptSkillSuggestion(threadId: string): Promise<void>;
  dismissSkillSuggestion(threadId: string): Promise<void>;
}

export function createClient(apiUrl: string): ApiClient {
  const base = apiUrl.replace(/\/$/, '');

  async function request(path: string, options?: RequestInit): Promise<Response> {
    const res = await fetch(`${base}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${await res.text()}`);
    return res;
  }

  return {
    async createThread() {
      const res = await request('/threads/', { method: 'POST', body: '{}' });
      const data = await res.json() as { thread_id: string };
      return data.thread_id;
    },

    async submitState(threadId, decisions) {
      await request(`/threads/${threadId}/state`, {
        method: 'POST',
        body: JSON.stringify({ values: { decisions } }),
      });
    },

    async acceptSkillSuggestion(threadId) {
      await request(`/threads/${threadId}/skill-suggestion/accept`, { method: 'POST' });
    },

    async dismissSkillSuggestion(threadId) {
      await request(`/threads/${threadId}/skill-suggestion/dismiss`, { method: 'POST' });
    },
  };
}
