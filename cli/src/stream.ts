import { Client } from '@langchain/langgraph-sdk';

export interface StreamChunk {
  event: string;
  data: Record<string, unknown>;
}

export async function* streamRun(
  apiUrl: string,
  threadId: string,
  input: Record<string, unknown> | null,
): AsyncGenerator<StreamChunk> {
  const client = new Client({ apiUrl });
  const stream = client.runs.stream(threadId, 'agent', {
    input,
    streamMode: ['messages', 'updates', 'custom', 'tasks'],
  });
  for await (const chunk of stream as AsyncIterable<StreamChunk>) {
    yield chunk;
  }
}
