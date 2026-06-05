import readline from 'readline';
import { execSync } from 'child_process';
import { loadConfig, configExists } from '../config.js';
import { createTheme } from '../theme.js';
import { runWizard } from '../wizard.js';
import { createClient } from '../client.js';
import { streamRun } from '../stream.js';
import { Renderer } from '../renderer.js';
import { handleHITL, type InterruptPayload } from '../hitl.js';

function getGitBranch(): string {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', { stdio: ['pipe', 'pipe', 'pipe'] })
      .toString()
      .trim();
  } catch {
    return 'no-git';
  }
}

async function getActiveModel(apiUrl: string): Promise<string> {
  try {
    const r = await fetch(`${apiUrl}/models/active`);
    const d = (await r.json()) as { name: string };
    return d.name;
  } catch {
    return 'unknown';
  }
}

export async function chatCommand(): Promise<void> {
  // First-run wizard
  let config = configExists() ? loadConfig() : await runWizard();

  const theme = createTheme(config.theme);
  const client = createClient(config.apiUrl);
  const renderer = new Renderer(theme);

  const branch = getGitBranch();
  const model = await getActiveModel(config.apiUrl);

  renderer.statusBar(branch, model);
  console.log(`🎼 Choreo CLI  输入 /help 查看命令，Ctrl+C 退出\n`);

  let threadId: string | null = null;

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  // Handle Ctrl+C gracefully
  rl.on('SIGINT', () => {
    console.log('\n再见！');
    process.exit(0);
  });

  const askUser = (): Promise<string> =>
    new Promise((resolve) => {
      process.stdout.write(`${theme.primary('❯')} `);
      rl.once('line', resolve);
    });

  while (true) {
    const input = await askUser();
    const trimmed = input.trim();
    if (!trimmed) continue;

    // Slash commands
    if (trimmed === '/quit' || trimmed === '/exit') {
      console.log('再见！');
      rl.close();
      process.exit(0);
    }

    if (trimmed === '/new') {
      threadId = null;
      renderer.info('已创建新对话');
      continue;
    }

    if (trimmed.startsWith('/thread ')) {
      threadId = trimmed.slice(8).trim();
      renderer.info(`已切换到线程 ${threadId}`);
      continue;
    }

    if (trimmed === '/config') {
      config = await runWizard();
      continue;
    }

    if (trimmed === '/help') {
      console.log([
        '',
        '  /new          创建新对话',
        '  /thread <id>  切换到指定线程',
        '  /config       重新配置',
        '  /quit         退出',
        '',
      ].join('\n'));
      continue;
    }

    // Ensure thread
    if (!threadId) {
      try {
        threadId = await client.createThread();
      } catch (e) {
        renderer.error(`无法连接后端: ${(e as Error).message}`);
        continue;
      }
    }

    // Stream message
    let streamInput: Record<string, unknown> | null = {
      messages: [{ role: 'human', content: trimmed }],
    };

    let interrupted = false;

    while (true) {
      try {
        let hasThinking = false;
        let thinkingEnded = false;

        for await (const chunk of streamRun(config.apiUrl, threadId, streamInput)) {
          // messages: tokens + thinking
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

          // updates: HITL interrupt
          if (chunk.event === 'updates') {
            const data = chunk.data as Record<string, unknown>;
            if (data.__interrupt__) {
              if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
              renderer.newline();
              const interruptValue = (data.__interrupt__ as InterruptPayload[])[0] as unknown as InterruptPayload;
              await handleHITL(interruptValue, client, renderer, threadId!);
              streamInput = null;
              interrupted = true;
              break;
            }
          }

          // tasks: alternative HITL signal
          if (chunk.event === 'tasks') {
            const task = chunk.data as { interrupts?: Array<{ value: InterruptPayload }> };
            if (task?.interrupts && task.interrupts.length > 0) {
              if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
              renderer.newline();
              const interruptValue = task.interrupts[0].value;
              await handleHITL(interruptValue, client, renderer, threadId!);
              streamInput = null;
              interrupted = true;
              break;
            }
          }

          // skill suggestion
          if (chunk.event === 'skill_suggestion') {
            const s = chunk.data as { category: string; name: string; description: string };
            renderer.skillSuggestion(s.category, s.name, s.description);
            const ans = await new Promise<string>((resolve) => rl.question('❯ ', resolve));
            if (ans.trim().toLowerCase() === 'y') {
              await client.acceptSkillSuggestion(threadId!).catch(() => {});
              renderer.success('技能已保存');
            } else {
              await client.dismissSkillSuggestion(threadId!).catch(() => {});
            }
          }

          // error
          if (chunk.event === 'error') {
            const errData = chunk.data as { message?: string };
            renderer.error(errData?.message ?? '未知错误');
          }
        }

        if (hasThinking && !thinkingEnded) { renderer.endThinking(); }

        if (!interrupted) break;
        interrupted = false;
        // continue inner while with streamInput = null (resume from interrupt)

      } catch (e) {
        renderer.error(`流式错误: ${(e as Error).message}`);
        break;
      }
    }

    renderer.newline();
  }
}
