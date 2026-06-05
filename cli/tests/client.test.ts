import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createClient } from '../src/client.js';

const mockFetch = vi.fn();
beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch);
  mockFetch.mockReset();
});

describe('createClient', () => {
  it('createThread calls POST /threads/ and returns thread_id', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ thread_id: 'abc123' }),
    });
    const client = createClient('http://localhost:8000');
    const id = await client.createThread();
    expect(id).toBe('abc123');
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/threads/',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('submitState calls POST /threads/{id}/state with decisions', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const client = createClient('http://localhost:8000');
    await client.submitState('tid1', [{ type: 'approve' }]);
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/threads/tid1/state',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ values: { decisions: [{ type: 'approve' }] } }),
      }),
    );
  });

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValue({ ok: false, text: async () => 'Not Found', status: 404 });
    const client = createClient('http://localhost:8000');
    await expect(client.createThread()).rejects.toThrow('HTTP 404');
  });
});
