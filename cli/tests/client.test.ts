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

describe('listModels', () => {
  it('returns model name list from /models/', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ name: 'deepseek-chat' }, { name: 'claude-sonnet-4-6' }],
    } as Response);
    const { createClient } = await import('../src/client.js');
    const client = createClient('http://localhost:8000');
    const models = await client.listModels();
    expect(models).toEqual([{ name: 'deepseek-chat' }, { name: 'claude-sonnet-4-6' }]);
    expect(fetch).toHaveBeenCalledWith('http://localhost:8000/models/', expect.any(Object));
  });
});

describe('getThreads', () => {
  it('returns thread list from /threads/', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [{ thread_id: 'abc-123', metadata: { title: 'test' } }],
    } as Response);
    const { createClient } = await import('../src/client.js');
    const client = createClient('http://localhost:8000');
    const threads = await client.getThreads();
    expect(threads[0].thread_id).toBe('abc-123');
  });
});
