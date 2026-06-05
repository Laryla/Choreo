import type { ChoreoConfig } from './config.js';
import type { ApiClient } from './client.js';
import type { Renderer } from './renderer.js';
import type { Theme } from './theme.js';

export interface CommandContext {
  config: ChoreoConfig;
  client: ApiClient;
  renderer: Renderer;
  theme: Theme;
  getThreadId: () => string | null;
  setThreadId: (id: string | null) => void;
  getCurrentModel: () => string;
  setCurrentModel: (name: string) => void;
  getBranch: () => string;
  askUser: () => Promise<string>;
}

export type CommandGroup = 'conversation' | 'thread' | 'model' | 'system';

export interface CommandDef {
  name: string;
  args?: string;
  description: string;
  group: CommandGroup;
  run: (args: string, ctx: CommandContext) => Promise<void>;
}

const GROUP_LABELS: Record<CommandGroup, string> = {
  conversation: '对话',
  thread: '线程',
  model: '模型 & 配置',
  system: '系统',
};

const GROUP_ORDER: CommandGroup[] = ['conversation', 'thread', 'model', 'system'];

const REGISTRY: CommandDef[] = [];

export function registerCommand(def: CommandDef): void {
  REGISTRY.push(def);
}

function printCommandList(ctx: CommandContext, cmds: CommandDef[]): void {
  process.stdout.write('\n');
  for (const group of GROUP_ORDER) {
    const inGroup = cmds.filter(c => c.group === group);
    if (!inGroup.length) continue;
    process.stdout.write(ctx.theme.dim(`  ${GROUP_LABELS[group]}\n`));
    for (const cmd of inGroup) {
      const nameStr = `/${cmd.name}`;
      const argsStr = cmd.args ? ` ${cmd.args}` : '';
      process.stdout.write(`    ${ctx.theme.primary(nameStr)}${ctx.theme.dim(argsStr)}\n`);
    }
  }
  process.stdout.write(ctx.theme.dim('\n  Tab 补全 · Enter 确认 · Esc 取消\n\n'));
}

export async function handleSlashInput(input: string, ctx: CommandContext): Promise<void> {
  let current = input;

  while (true) {
    const raw = current.slice(1).trim();
    const spaceIdx = raw.indexOf(' ');
    const cmdQuery = spaceIdx === -1 ? raw : raw.slice(0, spaceIdx);
    const argsStr  = spaceIdx === -1 ? '' : raw.slice(spaceIdx + 1);

    if (!cmdQuery) {
      printCommandList(ctx, REGISTRY);
      const next = (await ctx.askUser()).trim();
      if (!next.startsWith('/')) return;
      current = next;
      continue;
    }

    const matches = REGISTRY.filter(c => c.name.startsWith(cmdQuery));

    if (matches.length === 0) {
      ctx.renderer.error(`未知命令: /${cmdQuery}  (输入 /help 查看所有命令)`);
      return;
    }

    const exact = matches.find(c => c.name === cmdQuery);
    if (exact) {
      await exact.run(argsStr, ctx);
      return;
    }

    printCommandList(ctx, matches);
    const next = (await ctx.askUser()).trim();
    if (!next.startsWith('/')) return;
    current = next;
  }
}

// ── command: /new ──────────────────────────────────────────────
registerCommand({
  name: 'new',
  description: '新建对话',
  group: 'conversation',
  run: async (_, ctx) => {
    ctx.setThreadId(null);
    ctx.renderer.info('已创建新对话');
  },
});

// ── command: /clear ────────────────────────────────────────────
registerCommand({
  name: 'clear',
  description: '清屏，保留当前线程',
  group: 'conversation',
  run: async (_, ctx) => {
    process.stdout.write('\x1b[2J\x1b[H');
    ctx.renderer.statusBar(ctx.getBranch(), ctx.getCurrentModel());
  },
});

// ── command: /compact ──────────────────────────────────────────
registerCommand({
  name: 'compact',
  description: '压缩对话上下文',
  group: 'conversation',
  run: async (_, ctx) => {
    const tid = ctx.getThreadId();
    if (!tid) {
      ctx.renderer.error('无当前对话，请先发送消息');
      return;
    }
    ctx.renderer.info('压缩对话上下文...');
    const { streamRun } = await import('./stream.js');
    const COMPACT_PROMPT = '请将以上对话内容压缩为简短摘要，只保留关键信息和结论。用中文回复。';
    let hasOutput = false;
    try {
      for await (const chunk of streamRun(ctx.config.apiUrl, tid, {
        messages: [{ role: 'human', content: COMPACT_PROMPT }],
      }, ctx.getCurrentModel())) {
        if (chunk.event === 'messages') {
          const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs as Record<string, unknown>[]) {
            const content = msg?.content;
            if (typeof content === 'string' && content) {
              if (!hasOutput) process.stdout.write('\n');
              process.stdout.write(content);
              hasOutput = true;
            }
          }
        }
      }
      if (hasOutput) process.stdout.write('\n');
      ctx.renderer.success('摘要已添加到对话');
    } catch (e) {
      ctx.renderer.error(`压缩失败: ${(e as Error).message}`);
    }
  },
});

// ── command: /thread ───────────────────────────────────────────
registerCommand({
  name: 'thread',
  args: '<id>',
  description: '切换线程',
  group: 'thread',
  run: async (args, ctx) => {
    if (!args.trim()) {
      ctx.renderer.error('请提供线程 ID，例如: /thread abc-1234');
      return;
    }
    ctx.setThreadId(args.trim());
    ctx.renderer.success(`已切换到线程 ${args.trim()}`);
  },
});

// ── command: /history ──────────────────────────────────────────
registerCommand({
  name: 'history',
  description: '列出历史线程',
  group: 'thread',
  run: async (_, ctx) => {
    let threads: Awaited<ReturnType<typeof ctx.client.getThreads>>;
    try {
      threads = await ctx.client.getThreads();
    } catch (e) {
      ctx.renderer.error(`无法获取历史: ${(e as Error).message}`);
      return;
    }
    if (!threads.length) {
      ctx.renderer.info('暂无历史线程');
      return;
    }
    const current = ctx.getThreadId();
    process.stdout.write('\n');
    for (const t of threads.slice(0, 10)) {
      const marker = t.thread_id === current ? ctx.theme.success('●') : ctx.theme.dim('○');
      const shortId = t.thread_id.slice(0, 8) + '…';
      const title = (t.metadata?.title ?? '无标题').slice(0, 40);
      process.stdout.write(`  ${marker} ${ctx.theme.dim(shortId)}  ${title}\n`);
    }
    process.stdout.write(ctx.theme.dim('\n  输入线程 ID 前缀切换，直接回车取消\n'));
    const ans = (await ctx.askUser()).trim();
    if (!ans) return;
    const found = threads.find(t => t.thread_id.startsWith(ans));
    if (found) {
      ctx.setThreadId(found.thread_id);
      ctx.renderer.success(`已切换到 ${found.thread_id.slice(0, 8)}`);
    } else {
      ctx.renderer.error(`未找到线程: ${ans}`);
    }
  },
});

// ── command: /model ────────────────────────────────────────────
registerCommand({
  name: 'model',
  args: '[name]',
  description: '查看或切换模型',
  group: 'model',
  run: async (args, ctx) => {
    if (args.trim()) {
      let models: Awaited<ReturnType<typeof ctx.client.listModels>>;
      try {
        models = await ctx.client.listModels();
      } catch {
        // Can't validate — set anyway
        ctx.setCurrentModel(args.trim());
        ctx.renderer.success(`已切换到 ${args.trim()}（未验证）`);
        return;
      }
      const found = models.find(m => m.name === args.trim());
      if (found) {
        ctx.setCurrentModel(found.name);
        ctx.renderer.success(`已切换到 ${found.name}`);
      } else {
        ctx.renderer.error(`未知模型: ${args.trim()}`);
      }
      return;
    }
    let models: Awaited<ReturnType<typeof ctx.client.listModels>>;
    try {
      models = await ctx.client.listModels();
    } catch (e) {
      ctx.renderer.error(`无法获取模型列表: ${(e as Error).message}`);
      return;
    }
    const current = ctx.getCurrentModel();
    process.stdout.write('\n');
    for (const m of models) {
      const marker = m.name === current ? ctx.theme.success('●') : ctx.theme.dim('○');
      process.stdout.write(`  ${marker} ${m.name}\n`);
    }
    process.stdout.write(ctx.theme.dim('\n  输入模型名切换，直接回车取消\n'));
    const ans = (await ctx.askUser()).trim();
    if (!ans) return;
    const found = models.find(m => m.name === ans);
    if (found) {
      ctx.setCurrentModel(found.name);
      ctx.renderer.success(`已切换到 ${found.name}`);
    } else {
      ctx.renderer.error(`未知模型: ${ans}`);
    }
  },
});

// ── command: /config ───────────────────────────────────────────
registerCommand({
  name: 'config',
  description: '重新配置',
  group: 'model',
  run: async (_, ctx) => {
    const { runWizard } = await import('./wizard.js');
    const newConfig = await runWizard();
    Object.assign(ctx.config, newConfig);
    // Refresh active model in case apiUrl changed
    try {
      const res = await fetch(`${ctx.config.apiUrl}/models/active`);
      const d = await res.json() as { name: string };
      ctx.setCurrentModel(d.name);
    } catch { /* keep current model if backend unreachable */ }
  },
});

// ── command: /status ───────────────────────────────────────────
registerCommand({
  name: 'status',
  description: '连接状态',
  group: 'system',
  run: async (_, ctx) => {
    let connected = false;
    try {
      await ctx.client.listModels();
      connected = true;
    } catch { /* backend unreachable */ }
    const connStr = connected
      ? ctx.theme.success('● 已连接')
      : ctx.theme.error('✗ 无法连接');
    const tid = ctx.getThreadId() ?? ctx.theme.dim('(无)');
    const rows: [string, string][] = [
      ['后端', connStr],
      ['地址', ctx.config.apiUrl],
      ['线程', tid],
      ['模型', ctx.getCurrentModel()],
      ['分支', ctx.getBranch()],
    ];
    process.stdout.write('\n');
    for (const [k, v] of rows) {
      process.stdout.write(`  ${ctx.theme.dim(k.padEnd(6))}  ${v}\n`);
    }
    process.stdout.write('\n');
  },
});

// ── command: /help ─────────────────────────────────────────────
registerCommand({
  name: 'help',
  description: '显示帮助',
  group: 'system',
  run: async (_, ctx) => {
    printCommandList(ctx, REGISTRY);
  },
});

// ── command: /quit ─────────────────────────────────────────────
registerCommand({
  name: 'quit',
  description: '退出',
  group: 'system',
  run: async () => {
    process.stdout.write('再见！\n');
    process.exit(0);
  },
});
