import { Client } from '@langchain/langgraph-sdk';

export interface StreamChunk {
  event: string;
  data: unknown;
}

export async function* streamRun(
  apiUrl: string,
  threadId: string,
  input: Record<string, unknown> | null,
  modelName?: string,
): AsyncGenerator<StreamChunk> {
  const client = new Client({ apiUrl });
  const options: Record<string, unknown> = {
    input,
    streamMode: ['messages', 'updates', 'custom', 'tasks'],
  };
  if (modelName) {
    options.config = { configurable: { model_name: modelName } };
  }
  const stream = client.runs.stream(threadId, 'agent', options);
  for await (const chunk of stream as AsyncIterable<StreamChunk>) {
    yield chunk;
  }
}
