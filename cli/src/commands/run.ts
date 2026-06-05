import { loadConfig, configExists } from '../config.js';
import { runWizard } from '../wizard.js';
import { createTheme } from '../theme.js';
import { createClient } from '../client.js';
import { streamRun } from '../stream.js';
import { Renderer } from '../renderer.js';
import { handleHITL, type InterruptPayload } from '../hitl.js';

export async function runCommand(message: string): Promise<void> {
  const config = configExists() ? loadConfig() : await runWizard();
  const theme = createTheme(config.theme);
  const client = createClient(config.apiUrl);
  const renderer = new Renderer(theme);

  let threadId: string;
  try {
    threadId = await client.createThread();
  } catch (e) {
    renderer.error(`无法连接后端: ${(e as Error).message}`);
    process.exit(1);
  }

  let streamInput: Record<string, unknown> | null = {
    messages: [{ role: 'human', content: message }],
  };

  while (true) {
    let hasThinking = false;
    let thinkingEnded = false;
    let interrupted = false;

    try {
      for await (const chunk of streamRun(config.apiUrl, threadId, streamInput)) {
        if (chunk.event === 'messages') {
          const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs as Record<string, unknown>[]) {
            if (!msg) continue;
            const kwargs = msg.additional_kwargs as Record<string, unknown> | undefined;
            const reasoning = kwargs?.reasoning_content as string | undefined;
            if (reasoning) {
              if (!hasThinking) { renderer.startThinking(); hasThinking = true; }
              renderer.appendThinking(reasoning);
            }
            const content = msg.content;
            if (typeof content === 'string' && content) {
              if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
              renderer.appendToken(content);
            } else if (Array.isArray(content)) {
              for (const block of content as Record<string, unknown>[]) {
                if (block.type === 'thinking' || block.type === 'reasoning') {
                  if (!hasThinking) { renderer.startThinking(); hasThinking = true; }
                  renderer.appendThinking((block.thinking ?? block.reasoning ?? '') as string);
                } else if (block.type === 'text' && block.text) {
                  if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
                  renderer.appendToken(block.text as string);
                }
              }
            }
          }
        }

        if (chunk.event === 'updates') {
          const data = chunk.data as Record<string, unknown>;
          if (data.__interrupt__) {
            if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
            renderer.newline();
            const interruptValue = (data.__interrupt__ as InterruptPayload[])[0] as unknown as InterruptPayload;
            await handleHITL(interruptValue, client, renderer, threadId);
            streamInput = null;
            interrupted = true;
            break;
          }
        }

        if (chunk.event === 'tasks') {
          const task = chunk.data as { interrupts?: Array<{ value: InterruptPayload }> };
          if (task?.interrupts && task.interrupts.length > 0) {
            if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
            renderer.newline();
            const interruptValue = task.interrupts[0].value;
            await handleHITL(interruptValue, client, renderer, threadId);
            streamInput = null;
            interrupted = true;
            break;
          }
        }

        if (chunk.event === 'error') {
          const errData = chunk.data as { message?: string };
          renderer.error(errData?.message ?? '未知错误');
        }
      }

      if (hasThinking && !thinkingEnded) renderer.endThinking();
      if (!interrupted) break;

    } catch (e) {
      renderer.error(`流式错误: ${(e as Error).message}`);
      break;
    }
  }

  renderer.newline();
  process.exit(0);
}
