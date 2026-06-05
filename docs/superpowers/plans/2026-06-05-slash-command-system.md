# Slash Command System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Claude Code–style slash command picker to the Choreo CLI: typing `/` prints a grouped list of commands, typing `/m` filters to `/model`, and 10 built-in commands cover conversation, thread, model, and system operations.

**Architecture:** A new `cli/src/commands.ts` file holds the command registry (array of `CommandDef`), the `handleSlashInput()` selector logic (static list + prefix filter), and all command implementations. `chat.ts` is simplified from an if/else chain to a single `handleSlashInput()` call, with a `CommandContext` object wiring mutable state (threadId, currentModel) through closures. `client.ts` gains `listModels()` and `getThreads()`; `streamRun` gains an optional `modelName` parameter so `/model` switches take effect immediately.

**Tech Stack:** Node.js built-in `readline`, `chalk` via existing `Theme`, `@langchain/langgraph-sdk` Client (unchanged), `vitest` for tests.

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `cli/src/commands.ts` | **Create** | CommandDef interface, CommandContext interface, registry, selector, all 10 commands |
| `cli/src/client.ts` | **Modify** | Add `listModels()`, `getThreads()` to ApiClient |
| `cli/src/stream.ts` | **Modify** | Add optional `modelName` param → passed as `config.configurable.model_name` |
| `cli/src/commands/chat.ts` | **Modify** | Replace if/else chain with `handleSlashInput`; build `CommandContext`; pass model to stream |
| `cli/tests/commands.test.ts` | **Create** | Tests for selector logic |
| `cli/tests/client.test.ts` | **Modify** | Tests for `listModels`, `getThreads` |

---

## Task 1: Extend ApiClient

**Files:**
- Modify: `cli/src/client.ts`
- Modify: `cli/tests/client.test.ts`

### Step 1a — Write failing tests

Add to `cli/tests/client.test.ts` (after the existing `describe('createClient', ...)` block):

```ts
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
```

- [ ] Add the two `describe` blocks above to `cli/tests/client.test.ts` after the existing tests.

### Step 1b — Run tests to verify they fail

```bash
cd cli && npx vitest run tests/client.test.ts 2>&1 | tail -20
```

Expected: FAIL — `client.listModels is not a function`

- [ ] Run the command and confirm failure.

### Step 1c — Implement `listModels` and `getThreads`

Replace the entire `cli/src/client.ts` with:

```ts
export type DecisionType = 'approve' | 'reject' | 'edit';

export interface Decision {
  type: DecisionType;
  message?: string;
  edited_action?: { name: string; args: Record<string, unknown> };
}

export interface ModelInfo {
  name: string;
}

export interface ThreadInfo {
  thread_id: string;
  metadata?: { title?: string };
}

export interface ApiClient {
  createThread(): Promise<string>;
  submitState(threadId: string, decisions: Decision[]): Promise<void>;
  acceptSkillSuggestion(threadId: string): Promise<void>;
  dismissSkillSuggestion(threadId: string): Promise<void>;
  listModels(): Promise<ModelInfo[]>;
  getThreads(): Promise<ThreadInfo[]>;
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

    async listModels() {
      const res = await request('/models/');
      return res.json() as Promise<ModelInfo[]>;
    },

    async getThreads() {
      const res = await request('/threads/');
      return res.json() as Promise<ThreadInfo[]>;
    },
  };
}
```

- [ ] Replace `cli/src/client.ts` with the code above.

### Step 1d — Run tests to verify they pass

```bash
cd cli && npx vitest run tests/client.test.ts 2>&1 | tail -20
```

Expected: PASS (all tests including the 2 new ones)

- [ ] Run the command and confirm PASS.

### Step 1e — Commit

```bash
cd cli && git add src/client.ts tests/client.test.ts
git commit -m "feat(cli): add listModels and getThreads to ApiClient"
```

- [ ] Commit.

---

## Task 2: Update streamRun to accept modelName

**Files:**
- Modify: `cli/src/stream.ts`

No new tests needed — `stream.ts` wraps the SDK which is tested separately.

### Step 2a — Update `cli/src/stream.ts`

Replace the entire file:

```ts
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
```

- [ ] Replace `cli/src/stream.ts` with the code above.

### Step 2b — Commit

```bash
cd cli && git add src/stream.ts
git commit -m "feat(cli): pass model_name to LangGraph SDK via streamRun"
```

- [ ] Commit.

---

## Task 3: Command Registry and Selector (`commands.ts`)

**Files:**
- Create: `cli/src/commands.ts`
- Create: `cli/tests/commands.test.ts`

### Step 3a — Write failing tests

Create `cli/tests/commands.test.ts`:

```ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import type { CommandContext } from '../src/commands.js';

function makeCtx(overrides: Partial<CommandContext> = {}): CommandContext {
  return {
    config: { apiUrl: 'http://localhost:8000', theme: '#6366f1' },
    client: {
      createThread: vi.fn(),
      submitState: vi.fn(),
      acceptSkillSuggestion: vi.fn(),
      dismissSkillSuggestion: vi.fn(),
      listModels: vi.fn().mockResolvedValue([{ name: 'model-a' }, { name: 'model-b' }]),
      getThreads: vi.fn().mockResolvedValue([]),
    },
    renderer: {
      statusBar: vi.fn(),
      info: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      newline: vi.fn(),
      startThinking: vi.fn(),
      appendThinking: vi.fn(),
      endThinking: vi.fn(),
      expandThinking: vi.fn(),
      appendToken: vi.fn(),
      toolCallNormal: vi.fn(),
      toolCallDanger: vi.fn(),
      skillSuggestion: vi.fn(),
      prompt: vi.fn(),
      getThinkingLines: vi.fn().mockReturnValue([]),
    },
    theme: {
      primary: (s: string) => s,
      dim: (s: string) => s,
      success: (s: string) => s,
      error: (s: string) => s,
      warning: (s: string) => s,
      cyan: (s: string) => s,
      thinking: (s: string) => s,
      danger: (s: string) => s,
    },
    getThreadId: () => null,
    setThreadId: vi.fn(),
    getCurrentModel: () => 'deepseek-chat',
    setCurrentModel: vi.fn(),
    getBranch: () => 'main',
    askUser: vi.fn().mockResolvedValue(''),
    ...overrides,
  } as CommandContext;
}

describe('handleSlashInput', () => {
  let output: string;
  let writeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(async () => {
    output = '';
    writeSpy = vi.spyOn(process.stdout, 'write').mockImplementation((s: unknown) => {
      output += String(s);
      return true;
    });
  });

  afterEach(() => {
    writeSpy.mockRestore();
    vi.resetModules();
  });

  it('prints all commands when input is "/"', async () => {
    const { handleSlashInput } = await import('../src/commands.js');
    const ctx = makeCtx({ askUser: vi.fn().mockResolvedValue('') });
    await handleSlashInput('/', ctx);
    expect(output).toContain('/new');
    expect(output).toContain('/model');
    expect(output).toContain('/quit');
  });

  it('filters to matching commands when partial input given', async () => {
    const { handleSlashInput } = await import('../src/commands.js');
    const ctx = makeCtx({ askUser: vi.fn().mockResolvedValue('') });
    await handleSlashInput('/mo', ctx);
    expect(output).toContain('/model');
    expect(output).not.toContain('/new');
  });

  it('calls renderer.error for unknown command', async () => {
    const { handleSlashInput } = await import('../src/commands.js');
    const ctx = makeCtx();
    await handleSlashInput('/xyzzy', ctx);
    expect(ctx.renderer.error).toHaveBeenCalledWith(expect.stringContaining('xyzzy'));
  });

  it('executes /new when exact match', async () => {
    const { handleSlashInput } = await import('../src/commands.js');
    const ctx = makeCtx();
    await handleSlashInput('/new', ctx);
    expect(ctx.setThreadId).toHaveBeenCalledWith(null);
  });
});
```

- [ ] Create `cli/tests/commands.test.ts` with the code above.

### Step 3b — Run tests to verify they fail

```bash
cd cli && npx vitest run tests/commands.test.ts 2>&1 | tail -20
```

Expected: FAIL — `Cannot find module '../src/commands.js'`

- [ ] Run and confirm failure.

### Step 3c — Create `cli/src/commands.ts` with registry + selector

Create `cli/src/commands.ts`:

```ts
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
  const raw = input.slice(1).trim();        // remove leading "/"
  const spaceIdx = raw.indexOf(' ');
  const cmdQuery = spaceIdx === -1 ? raw : raw.slice(0, spaceIdx);
  const argsStr  = spaceIdx === -1 ? '' : raw.slice(spaceIdx + 1);

  if (!cmdQuery) {
    // bare "/" — show full list and ask again
    printCommandList(ctx, REGISTRY);
    const next = (await ctx.askUser()).trim();
    if (next.startsWith('/')) await handleSlashInput(next, ctx);
    return;
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

  // partial match — show filtered list and ask again
  printCommandList(ctx, matches);
  const next = (await ctx.askUser()).trim();
  if (next.startsWith('/')) await handleSlashInput(next, ctx);
}
```

- [ ] Create `cli/src/commands.ts` with the code above.

### Step 3d — Run tests to verify they pass

```bash
cd cli && npx vitest run tests/commands.test.ts 2>&1 | tail -20
```

Expected: PASS (4 tests pass)

- [ ] Run and confirm PASS.

### Step 3e — Commit

```bash
cd cli && git add src/commands.ts tests/commands.test.ts
git commit -m "feat(cli): add command registry and slash command selector"
```

- [ ] Commit.

---

## Task 4: Register All Commands

**Files:**
- Modify: `cli/src/commands.ts` (append to bottom, after `handleSlashInput`)

All 10 commands are appended to `commands.ts`. Each block calls `registerCommand()` at module load time.

### Step 4a — Append all command registrations to `cli/src/commands.ts`

Append the following block **after the `handleSlashInput` function** in `cli/src/commands.ts`:

```ts
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
    let tokenCount = 0;
    try {
      for await (const chunk of streamRun(ctx.config.apiUrl, tid, {
        messages: [{ role: 'human', content: COMPACT_PROMPT }],
      })) {
        if (chunk.event === 'messages') {
          const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
          for (const msg of msgs as Record<string, unknown>[]) {
            const content = msg?.content;
            if (typeof content === 'string' && content) {
              if (tokenCount === 0) process.stdout.write('\n');
              process.stdout.write(content);
              tokenCount++;
            }
          }
        }
      }
      if (tokenCount > 0) process.stdout.write('\n');
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
      ctx.setCurrentModel(args.trim());
      ctx.renderer.success(`已切换到 ${args.trim()}`);
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
      const res = await fetch(`${ctx.config.apiUrl}/models/active`);
      connected = res.ok;
    } catch { /* unreachable */ }
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
```

- [ ] Append the block above to the end of `cli/src/commands.ts`.

### Step 4b — Run all tests to verify nothing broke

```bash
cd cli && npx vitest run 2>&1 | tail -20
```

Expected: all existing tests PASS (the 4 `commands.test.ts` tests still pass; nothing in commands.ts changes the test surface).

- [ ] Run and confirm PASS.

### Step 4c — Commit

```bash
cd cli && git add src/commands.ts
git commit -m "feat(cli): register all 10 built-in slash commands"
```

- [ ] Commit.

---

## Task 5: Integrate into chat.ts

**Files:**
- Modify: `cli/src/commands/chat.ts`

This is the biggest change: replace the hardcoded if/else chain with `handleSlashInput`, build the `CommandContext`, and thread `currentModel` through the stream call.

### Step 5a — Replace `cli/src/commands/chat.ts` entirely

```ts
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
  let config = configExists() ? loadConfig() : await runWizard();

  const theme = createTheme(config.theme);
  const client = createClient(config.apiUrl);
  const renderer = new Renderer(theme);

  const branch = getGitBranch();
  let currentModel = await getActiveModel(config.apiUrl);

  renderer.statusBar(branch, currentModel);
  console.log(`🎼 Choreo CLI  输入 /help 查看命令，Ctrl+C 退出\n`);

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

    // Stream message
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
```

- [ ] Replace `cli/src/commands/chat.ts` with the code above.

### Step 5b — Run all tests

```bash
cd cli && npx vitest run 2>&1 | tail -20
```

Expected: all tests PASS (13 existing + 4 new commands tests = 17 total)

- [ ] Run and confirm PASS.

### Step 5c — Smoke test

With the backend running (`cd backend && uv run uvicorn choreo.gateway.app:app --reload`):

```bash
cd cli && npx tsx src/index.ts
```

Verify:
1. Type `/` + Enter → grouped command list appears
2. Type `/m` + Enter → only `/model` shown
3. Type `/model` + Enter → model list appears
4. Type `/status` + Enter → connection info shown
5. Type `/new` + Enter → "已创建新对话"
6. Type `/clear` + Enter → screen clears, status bar re-appears
7. Type `/quit` + Enter → exits

- [ ] Manually verify all 7 behaviours above.

### Step 5d — Commit

```bash
cd cli && git add src/commands/chat.ts
git commit -m "feat(cli): integrate slash command selector into chat REPL"
```

- [ ] Commit.

---

## Verification Against Spec

| Acceptance criterion | Covered by |
|---------------------|------------|
| `/` prints grouped command list | Task 3 selector + Task 4 registrations |
| `/m` filters to `/model`, Enter executes | Task 3 selector logic |
| `/model` lists models, Enter to switch, status bar updates | Task 4 `/model` + Task 5 `currentModel` |
| `/status` shows backend, thread, model, branch | Task 4 `/status` |
| `/compact` sends compact prompt, streams response | Task 4 `/compact` |
| `/history` lists threads, picks by ID prefix | Task 4 `/history` |
| `/clear` clears screen, status bar re-renders | Task 4 `/clear` |
| `/help` reuses command list style | Task 4 `/help` |
| Existing commands unchanged (behaviour) | Task 4 registrations + Task 5 |
| `modelName` from `/model` used in next stream call | Task 2 `streamRun` + Task 5 `currentModel` |
