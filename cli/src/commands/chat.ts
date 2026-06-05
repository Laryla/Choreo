import readline from 'readline';
import { execSync } from 'child_process';
import { loadConfig, configExists } from '../config.js';
import { createTheme } from '../theme.js';
import { runWizard } from '../wizard.js';
import { createClient } from '../client.js';
import { streamRun } from '../stream.js';
import { Renderer } from '../renderer.js';
import { handleHITL, type InterruptPayload } from '../hitl.js';
import { handleSlashInput, type CommandContext } from '../commands.js';

function getGitBranch(): string {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', { stdio: ['pipe', 'pipe', 'pipe'] })
      .toString()
      .trim();
  } catch {
    return 'no-git';
  }
}

async function printStartup(apiUrl: string, branch: string, theme: ReturnType<typeof createTheme>): Promise<{ model: string; connected: boolean }> {
  const o = process.stdout;

  // ① Logo
  o.write(`\n  ${theme.primary('🎼  CHOREO')}  ${theme.dim('v0.1.0')}\n\n`);

  // ② Check backend
  let connected = false;
  let model = 'unknown';
  try {
    const r = await fetch(`${apiUrl}/models/active`);
    if (r.ok) {
      connected = true;
      const d = (await r.json()) as { name: string };
      model = d.name;
    }
  } catch { /* offline */ }

  const ok  = (s: string) => theme.success('✓') + '  ' + s;
  const err = (s: string) => theme.error('✗') + '  ' + s;
  const dim = theme.dim.bind(theme);
  const hint = (s: string) => `  ${theme.dim(s)}`;

  // 后端行
  if (connected) {
    o.write(`  ${ok(dim('后端') + '  ')}${theme.success(apiUrl.replace(/^https?:\/\//, ''))}\n`);
  } else {
    o.write(`  ${err(dim('后端') + '  ')}${theme.error('无法连接 ' + apiUrl.replace(/^https?:\/\//, ''))}\n`);
    o.write(`${hint('/config 修改地址，连接后自动重试')}\n`);
  }

  // 模型行
  o.write(`  ${ok(dim('模型') + '  ')}${theme.cyan(model)}${hint('  /model 切换')}\n`);

  // 分支行
  o.write(`  ${ok(dim('分支') + '  ')}${theme.success(branch)}\n`);

  // 线程行
  o.write(`  ${ok(dim('线程') + '  ')}${dim('新建')}${hint('  /history 恢复历史')}\n`);

  // ③ 分隔 + 提示
  o.write(`\n  ${dim('─'.repeat(44))}\n`);
  o.write(`  ${dim('/')} 浏览命令  ·  ${dim('Ctrl+C')} 退出\n`);
  o.write(`  ${dim('─'.repeat(44))}\n\n`);

  return { model, connected };
}

export async function chatCommand(): Promise<void> {
  let config = configExists() ? loadConfig() : await runWizard();

  const theme = createTheme(config.theme);
  const client = createClient(config.apiUrl);
  const renderer = new Renderer(theme);

  const branch = getGitBranch();
  const { model } = await printStartup(config.apiUrl, branch, theme);
  let currentModel = model;

  let threadId: string | null = null;

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  rl.on('SIGINT', () => {
    process.stdout.write('\n再见！\n');
    process.exit(0);
  });

  const askUser = (): Promise<string> =>
    new Promise((resolve) => {
      process.stdout.write(`${theme.primary('❯')} `);
      rl.once('line', resolve);
    });

  // CommandContext wires mutable state through closures
  const ctx: CommandContext = {
    config,
    client,
    renderer,
    theme,
    getThreadId: () => threadId,
    setThreadId: (id) => { threadId = id; },
    getCurrentModel: () => currentModel,
    setCurrentModel: (name) => { currentModel = name; },
    getBranch: () => branch,
    askUser,
  };

  while (true) {
    const input = await askUser();
    const trimmed = input.trim();
    if (!trimmed) continue;

    // Slash commands → delegate to registry
    if (trimmed.startsWith('/')) {
      await handleSlashInput(trimmed, ctx);
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

    // Stream message — pass currentModel so /model changes take effect
    let streamInput: Record<string, unknown> | null = {
      messages: [{ role: 'human', content: trimmed }],
    };

    let interrupted = false;

    while (true) {
      try {
        let hasThinking = false;
        let thinkingEnded = false;

        for await (const chunk of streamRun(config.apiUrl, threadId, streamInput, currentModel)) {
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
              await handleHITL(interruptValue, client, renderer, threadId!);
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
              await handleHITL(interruptValue, client, renderer, threadId!);
              streamInput = null;
              interrupted = true;
              break;
            }
          }

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

          if (chunk.event === 'error') {
            const errData = chunk.data as { message?: string };
            renderer.error(errData?.message ?? '未知错误');
          }
        }

        if (hasThinking && !thinkingEnded) { renderer.endThinking(); }
        if (!interrupted) break;
        interrupted = false;

      } catch (e) {
        renderer.error(`流式错误: ${(e as Error).message}`);
        break;
      }
    }

    renderer.newline();
  }
}
