# Choreo CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a TypeScript CLI (`choreo`) that talks to the existing FastAPI backend, streams AI responses in the terminal with Claude Code-style UI, and supports HITL tool confirmation.

**Architecture:** New `cli/` directory at the project root, independent npm package. Connects to `http://localhost:8000` (configurable) using `@langchain/langgraph-sdk` for SSE streaming — the same SDK already used by the React frontend. All rendering via `chalk` + `process.stdout.write`. No backend changes required.

**Tech Stack:** TypeScript 5, Node.js 22, ESM (`"type":"module"`), chalk 5, inquirer 9, ora 8, commander 12, @langchain/langgraph-sdk, tsx (dev), tsup (build), vitest (tests)

---

## File Structure

```
cli/
├── src/
│   ├── index.ts           ← commander entry, registers chat + run commands
│   ├── config.ts          ← read/write ~/.choreo/config.json
│   ├── theme.ts           ← chalk color factory from hex string
│   ├── wizard.ts          ← first-run interactive setup (inquirer)
│   ├── client.ts          ← REST API calls (createThread, submitState, etc.)
│   ├── stream.ts          ← SSE consumer via @langchain/langgraph-sdk
│   ├── renderer.ts        ← terminal output (status bar, tokens, tool calls, HITL)
│   ├── hitl.ts            ← HITL readline prompt + isDangerous() detection
│   └── commands/
│       ├── chat.ts        ← interactive REPL loop
│       └── run.ts         ← single-shot non-interactive run
├── tests/
│   ├── config.test.ts
│   ├── theme.test.ts
│   ├── client.test.ts
│   └── hitl.test.ts
├── package.json
└── tsconfig.json
```

---

## Task 1: Project Scaffold

**Files:**
- Create: `cli/package.json`
- Create: `cli/tsconfig.json`
- Create: `cli/src/index.ts`

- [ ] **Step 1: Create `cli/package.json`**

```json
{
  "name": "@choreo/cli",
  "version": "0.1.0",
  "description": "Choreo AI assistant CLI",
  "type": "module",
  "bin": { "choreo": "./dist/index.js" },
  "scripts": {
    "dev": "tsx src/index.ts",
    "build": "tsup src/index.ts --format esm --dts",
    "test": "vitest run"
  },
  "dependencies": {
    "@langchain/langgraph-sdk": "latest",
    "chalk": "^5.4.1",
    "commander": "^12.1.0",
    "inquirer": "^9.3.7",
    "ora": "^8.1.1"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "tsup": "^8.3.0",
    "tsx": "^4.19.0",
    "typescript": "^5.6.2",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Create `cli/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "./dist",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true
  },
  "include": ["src/**/*", "tests/**/*"]
}
```

- [ ] **Step 3: Create `cli/src/index.ts`**

```ts
#!/usr/bin/env node
import { Command } from 'commander';
import { chatCommand } from './commands/chat.js';
import { runCommand } from './commands/run.js';

const program = new Command();

program
  .name('choreo')
  .description('Choreo AI assistant CLI')
  .version('0.1.0');

program
  .command('run <message>', { isDefault: false })
  .description('Send a single message and exit')
  .action(runCommand);

// Default: interactive chat
program
  .action(chatCommand);

program.parse();
```

- [ ] **Step 4: Install dependencies**

```bash
cd cli && npm install
```

Expected: `node_modules/` created, no errors.

- [ ] **Step 5: Verify entry point runs**

```bash
cd cli && npx tsx src/index.ts --help
```

Expected output:
```
Usage: choreo [options] [command]

Choreo AI assistant CLI

Options:
  -V, --version   output the version number
  -h, --help      display help for command
```

- [ ] **Step 6: Commit**

```bash
git add cli/
git commit -m "feat(cli): project scaffold — package.json, tsconfig, entry point"
```

---

## Task 2: Config + Theme

**Files:**
- Create: `cli/src/config.ts`
- Create: `cli/src/theme.ts`
- Create: `cli/tests/config.test.ts`
- Create: `cli/tests/theme.test.ts`

- [ ] **Step 1: Write failing tests for config**

```ts
// cli/tests/config.test.ts
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { tmpdir } from 'os';
import { join } from 'path';
import { writeFileSync, mkdirSync, rmSync, existsSync } from 'fs';

// We'll test the pure logic by pointing HOME at a temp dir
const tmpHome = join(tmpdir(), `choreo-test-${Date.now()}`);

beforeEach(() => mkdirSync(tmpHome, { recursive: true }));
afterEach(() => rmSync(tmpHome, { recursive: true, force: true }));

describe('loadConfig', () => {
  it('returns defaults when no config file exists', async () => {
    process.env.HOME = tmpHome;
    const { loadConfig } = await import('../src/config.js');
    const cfg = loadConfig();
    expect(cfg.apiUrl).toBe('http://localhost:8000');
    expect(cfg.theme).toBe('#6366f1');
  });

  it('merges saved values over defaults', async () => {
    const dir = join(tmpHome, '.choreo');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'config.json'), JSON.stringify({ theme: '#f43f5e' }));
    process.env.HOME = tmpHome;
    const { loadConfig } = await import('../src/config.js?v=2');
    const cfg = loadConfig();
    expect(cfg.theme).toBe('#f43f5e');
    expect(cfg.apiUrl).toBe('http://localhost:8000');
  });
});

describe('configExists', () => {
  it('returns false when file missing', async () => {
    process.env.HOME = tmpHome;
    const { configExists } = await import('../src/config.js?v=3');
    expect(configExists()).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd cli && npx vitest run tests/config.test.ts
```

Expected: FAIL — `Cannot find module '../src/config.js'`

- [ ] **Step 3: Create `cli/src/config.ts`**

```ts
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { homedir } from 'os';
import { join } from 'path';

export interface ChoreoConfig {
  apiUrl: string;
  theme: string;
}

const CONFIG_DIR = join(homedir(), '.choreo');
const CONFIG_PATH = join(CONFIG_DIR, 'config.json');

const DEFAULT_CONFIG: ChoreoConfig = {
  apiUrl: process.env.CHOREO_API_URL ?? 'http://localhost:8000',
  theme: '#6366f1',
};

export function loadConfig(): ChoreoConfig {
  if (!existsSync(CONFIG_PATH)) return { ...DEFAULT_CONFIG };
  try {
    return { ...DEFAULT_CONFIG, ...JSON.parse(readFileSync(CONFIG_PATH, 'utf-8')) };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

export function saveConfig(config: ChoreoConfig): void {
  if (!existsSync(CONFIG_DIR)) mkdirSync(CONFIG_DIR, { recursive: true });
  writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
}

export function configExists(): boolean {
  return existsSync(CONFIG_PATH);
}
```

- [ ] **Step 4: Write failing test for theme**

```ts
// cli/tests/theme.test.ts
import { describe, it, expect } from 'vitest';
import { createTheme } from '../src/theme.js';

describe('createTheme', () => {
  it('returns callable functions for all color roles', () => {
    const theme = createTheme('#6366f1');
    expect(typeof theme.primary('x')).toBe('string');
    expect(typeof theme.success('x')).toBe('string');
    expect(typeof theme.error('x')).toBe('string');
    expect(typeof theme.danger('x')).toBe('string');
    expect(typeof theme.dim('x')).toBe('string');
    expect(typeof theme.cyan('x')).toBe('string');
    expect(typeof theme.thinking('x')).toBe('string');
    expect(typeof theme.warning('x')).toBe('string');
  });

  it('primary color uses the provided hex', () => {
    const theme = createTheme('#ff0000');
    // chalk wraps text in ANSI codes — just verify it contains the input text
    expect(theme.primary('hello')).toContain('hello');
  });
});
```

- [ ] **Step 5: Create `cli/src/theme.ts`**

```ts
import chalk from 'chalk';

export interface Theme {
  primary:  (t: string) => string;
  dim:      (t: string) => string;
  success:  (t: string) => string;
  error:    (t: string) => string;
  warning:  (t: string) => string;
  cyan:     (t: string) => string;
  thinking: (t: string) => string;
  danger:   (t: string) => string;
}

export function createTheme(hexColor: string): Theme {
  return {
    primary:  (t) => chalk.hex(hexColor)(t),
    dim:      (t) => chalk.hex('#475569')(t),
    success:  (t) => chalk.hex('#4ade80')(t),
    error:    (t) => chalk.hex('#f87171')(t),
    warning:  (t) => chalk.hex('#fbbf24')(t),
    cyan:     (t) => chalk.hex('#67e8f9')(t),
    thinking: (t) => chalk.hex('#334155')(t),
    danger:   (t) => chalk.hex('#f43f5e')(t),
  };
}
```

- [ ] **Step 6: Run all tests to verify they pass**

```bash
cd cli && npx vitest run
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add cli/src/config.ts cli/src/theme.ts cli/tests/
git commit -m "feat(cli): config persistence and theme system"
```

---

## Task 3: First-Run Wizard

**Files:**
- Create: `cli/src/wizard.ts`

- [ ] **Step 1: Create `cli/src/wizard.ts`**

```ts
import inquirer from 'inquirer';
import chalk from 'chalk';
import { saveConfig, type ChoreoConfig } from './config.js';

const PRESET_THEMES = [
  { name: `Indigo 紫  ${chalk.hex('#6366f1')('████')}`, value: '#6366f1' },
  { name: `Emerald 绿 ${chalk.hex('#10b981')('████')}`, value: '#10b981' },
  { name: `Sky 蓝     ${chalk.hex('#0ea5e9')('████')}`, value: '#0ea5e9' },
  { name: `Rose 玫红  ${chalk.hex('#f43f5e')('████')}`, value: '#f43f5e' },
  { name: `Amber 琥珀 ${chalk.hex('#f59e0b')('████')}`, value: '#f59e0b' },
  { name: '自定义...', value: '__custom__' },
];

export async function runWizard(): Promise<ChoreoConfig> {
  console.log('\n👋 欢迎使用 Choreo CLI！先做个简单配置。\n');

  const { apiUrl } = await inquirer.prompt([
    {
      type: 'input',
      name: 'apiUrl',
      message: '后端 API 地址:',
      default: process.env.CHOREO_API_URL ?? 'http://localhost:8000',
    },
  ]);

  const { themeChoice } = await inquirer.prompt([
    {
      type: 'list',
      name: 'themeChoice',
      message: '选择主题色:',
      choices: PRESET_THEMES,
    },
  ]);

  let theme = themeChoice;
  if (themeChoice === '__custom__') {
    const { customColor } = await inquirer.prompt([
      {
        type: 'input',
        name: 'customColor',
        message: '输入颜色 (hex, 如 #ff6b35):',
        validate: (v: string) => /^#[0-9a-fA-F]{6}$/.test(v) || '请输入有效 hex 颜色',
      },
    ]);
    theme = customColor;
  }

  const config: ChoreoConfig = { apiUrl, theme };
  saveConfig(config);
  console.log(chalk.hex('#4ade80')('\n✓ 配置已保存到 ~/.choreo/config.json\n'));
  return config;
}
```

- [ ] **Step 2: Verify wizard can be imported**

```bash
cd cli && npx tsx -e "import('./src/wizard.js').then(() => console.log('ok'))"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add cli/src/wizard.ts
git commit -m "feat(cli): first-run interactive setup wizard"
```

---

## Task 4: API Client

**Files:**
- Create: `cli/src/client.ts`
- Create: `cli/tests/client.test.ts`

- [ ] **Step 1: Write failing tests**

```ts
// cli/tests/client.test.ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd cli && npx vitest run tests/client.test.ts
```

Expected: FAIL — `Cannot find module '../src/client.js'`

- [ ] **Step 3: Create `cli/src/client.ts`**

```ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd cli && npx vitest run tests/client.test.ts
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add cli/src/client.ts cli/tests/client.test.ts
git commit -m "feat(cli): backend API client with tests"
```

---

## Task 5: SSE Stream Consumer

**Files:**
- Create: `cli/src/stream.ts`

- [ ] **Step 1: Create `cli/src/stream.ts`**

```ts
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
```

- [ ] **Step 2: Verify import resolves**

```bash
cd cli && npx tsx -e "import('./src/stream.js').then(() => console.log('ok'))"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add cli/src/stream.ts
git commit -m "feat(cli): SSE stream consumer via langgraph-sdk"
```

---

## Task 6: Terminal Renderer

**Files:**
- Create: `cli/src/renderer.ts`

- [ ] **Step 1: Create `cli/src/renderer.ts`**

```ts
import chalk from 'chalk';
import type { Theme } from './theme.js';

export class Renderer {
  private thinkingLines: string[] = [];
  private isThinking = false;

  constructor(private theme: Theme) {}

  statusBar(branch: string, model: string): void {
    const logo = this.theme.primary('◉ Choreo');
    const sep = this.theme.dim(' · ');
    const br = chalk.hex('#4ade80')(branch);
    const mdl = chalk.hex('#60a5fa')(model);
    process.stdout.write(`${logo}${sep}${br}${sep}${mdl}\n\n`);
  }

  startThinking(): void {
    this.isThinking = true;
    this.thinkingLines = [];
    process.stdout.write(this.theme.dim('💭 思考中...\n'));
  }

  appendThinking(text: string): void {
    if (!this.isThinking) {
      this.isThinking = true;
      this.thinkingLines = [];
      process.stdout.write(this.theme.dim('💭 思考中...\n'));
    }
    this.thinkingLines.push(...text.split('\n').filter(Boolean));
  }

  endThinking(): void {
    if (!this.isThinking) return;
    this.isThinking = false;
    const count = Math.max(this.thinkingLines.length, 1);
    // overwrite "思考中..." line
    process.stdout.write(`\x1b[1A\x1b[2K`);
    process.stdout.write(this.theme.dim(`💭 已思考 ${count} 步 ▶  (回车展开)\n`));
  }

  expandThinking(): void {
    process.stdout.write(this.theme.dim('💭 思考过程 ▼\n'));
    for (const line of this.thinkingLines) {
      process.stdout.write(this.theme.thinking(`  ╎ ${line}\n`));
    }
    process.stdout.write('\n');
  }

  appendToken(text: string): void {
    process.stdout.write(chalk.hex('#e2e8f0')(text));
  }

  toolCallNormal(name: string, command: string): void {
    const maxWidth = 56;
    const inner = command.length > maxWidth ? command.slice(0, maxWidth - 3) + '...' : command;
    const pad = '─'.repeat(Math.max(0, maxWidth - name.length - 3));
    process.stdout.write('\n');
    process.stdout.write(this.theme.dim(`┌─ ${name} ${pad}┐\n`));
    process.stdout.write(`│ ${this.theme.cyan(inner.padEnd(maxWidth - 2))}\n`);
    process.stdout.write(this.theme.dim(`└${'─'.repeat(maxWidth + 1)}┘\n`));
  }

  toolCallDanger(name: string, command: string): void {
    process.stdout.write('\n');
    process.stdout.write(this.theme.danger(`⚠ ${name}`) + chalk.bgHex('#4c0519').hex('#fda4af')(' 危险操作 ') + '\n');
    process.stdout.write(chalk.hex('#e2e8f0')(`  ${command}\n`));
    process.stdout.write(this.theme.danger('─'.repeat(58) + '\n'));
  }

  success(text: string): void {
    process.stdout.write(`${this.theme.success('✓')} ${chalk.hex('#e2e8f0')(text)}\n`);
  }

  error(text: string): void {
    process.stdout.write(`\n${this.theme.error('✗ ' + text)}\n`);
  }

  skillSuggestion(category: string, name: string, description: string): void {
    const title = `💡 建议保存为技能：${category}/${name}`;
    const desc = description.slice(0, 52);
    const w = 60;
    const pad = (s: string) => s + ' '.repeat(Math.max(0, w - 4 - s.length));
    process.stdout.write('\n');
    process.stdout.write(this.theme.warning(`╭${'─'.repeat(w - 2)}╮\n`));
    process.stdout.write(this.theme.warning(`│ ${pad(title)} │\n`));
    process.stdout.write(this.theme.dim(`│ ${pad(desc)} │\n`));
    process.stdout.write(this.theme.warning(`│ ${pad('[y] 保存  [n] 忽略')} │\n`));
    process.stdout.write(this.theme.warning(`╰${'─'.repeat(w - 2)}╯\n`));
  }

  prompt(): void {
    process.stdout.write(`\n${this.theme.primary('❯')} `);
  }

  newline(): void {
    process.stdout.write('\n');
  }

  info(text: string): void {
    process.stdout.write(this.theme.dim(`  ${text}\n`));
  }

  getThinkingLines(): string[] {
    return [...this.thinkingLines];
  }
}
```

- [ ] **Step 2: Verify import resolves**

```bash
cd cli && npx tsx -e "import('./src/renderer.js').then(() => console.log('ok'))"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add cli/src/renderer.ts
git commit -m "feat(cli): terminal renderer with thinking blocks, tool calls, HITL display"
```

---

## Task 7: HITL Interaction

**Files:**
- Create: `cli/src/hitl.ts`
- Create: `cli/tests/hitl.test.ts`

- [ ] **Step 1: Write failing tests for `isDangerous`**

```ts
// cli/tests/hitl.test.ts
import { describe, it, expect } from 'vitest';
import { isDangerous } from '../src/hitl.js';

describe('isDangerous', () => {
  it('flags rm -rf', () => {
    expect(isDangerous('rm -rf ./logs')).toBe(true);
    expect(isDangerous('rm -r /tmp/foo')).toBe(true);
  });

  it('flags git push --force', () => {
    expect(isDangerous('git push origin main --force')).toBe(true);
    expect(isDangerous('git push --force-with-lease')).toBe(true);
  });

  it('flags SQL destructive ops', () => {
    expect(isDangerous('DROP TABLE users')).toBe(true);
    expect(isDangerous('TRUNCATE TABLE logs')).toBe(true);
    expect(isDangerous('DELETE FROM sessions')).toBe(true);
  });

  it('does not flag safe commands', () => {
    expect(isDangerous('git status')).toBe(false);
    expect(isDangerous('ls -la')).toBe(false);
    expect(isDangerous('git add -A')).toBe(false);
    expect(isDangerous('npm install')).toBe(false);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd cli && npx vitest run tests/hitl.test.ts
```

Expected: FAIL — `Cannot find module '../src/hitl.js'`

- [ ] **Step 3: Create `cli/src/hitl.ts`**

```ts
import readline from 'readline';
import type { ApiClient, Decision } from './client.js';
import type { Renderer } from './renderer.js';

const DANGEROUS_PATTERNS = [
  /rm\s+-[rf]/,
  /git\s+push\s+.*--force/i,
  /git\s+push\s+--force/i,
  /DROP\s+TABLE/i,
  /TRUNCATE\s+TABLE/i,
  /DELETE\s+FROM/i,
  /mkfs/,
  /dd\s+if=/,
  /chmod\s+-R\s+777/,
];

export function isDangerous(command: string): boolean {
  return DANGEROUS_PATTERNS.some((p) => p.test(command));
}

export interface InterruptPayload {
  action_requests: Array<{ name: string; arguments: Record<string, unknown> }>;
  review_configs?: Array<{ action_name: string; allowed_decisions: string[] }>;
}

function ask(rl: readline.Interface, question: string): Promise<string> {
  return new Promise((resolve) => rl.question(question, resolve));
}

export async function handleHITL(
  payload: InterruptPayload,
  client: ApiClient,
  renderer: Renderer,
  threadId: string,
): Promise<void> {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  for (const req of payload.action_requests) {
    const command = (req.arguments.command ?? JSON.stringify(req.arguments)) as string;
    const dangerous = isDangerous(command);

    if (dangerous) {
      renderer.toolCallDanger(req.name, command);
    } else {
      renderer.toolCallNormal(req.name, command);
    }

    const hint = dangerous
      ? '[y] 确认执行  [n] 拒绝  [e] 编辑命令'
      : '[y] 执行  [n] 拒绝  [e] 编辑  [!] 之后全部允许';

    process.stdout.write(`${hint}\n`);
    const answer = (await ask(rl, '❯ ')).trim().toLowerCase();

    let decision: Decision;

    if (answer === 'y' || answer === '') {
      decision = { type: 'approve' };
    } else if (answer === 'n') {
      decision = { type: 'reject' };
    } else if (answer === 'e') {
      const edited = await ask(rl, '新命令: ');
      decision = {
        type: 'edit',
        edited_action: { name: req.name, args: { command: edited.trim() } },
      };
    } else if (answer === '!') {
      decision = { type: 'approve' };
      // TODO: persist "allow all" flag for this session
    } else {
      decision = { type: 'reject' };
    }

    await client.submitState(threadId, [decision]);
  }

  rl.close();
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd cli && npx vitest run tests/hitl.test.ts
```

Expected: all `isDangerous` tests pass.

- [ ] **Step 5: Commit**

```bash
git add cli/src/hitl.ts cli/tests/hitl.test.ts
git commit -m "feat(cli): HITL smart-grading prompt with isDangerous detection"
```

---

## Task 8: Chat Command (Interactive REPL)

**Files:**
- Create: `cli/src/commands/chat.ts`

- [ ] **Step 1: Create `cli/src/commands/chat.ts`**

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

function getGitBranch(): string {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', { stdio: ['pipe', 'pipe', 'pipe'] })
      .toString()
      .trim();
  } catch {
    return 'no-git';
  }
}

function getActiveModel(apiUrl: string): Promise<string> {
  return fetch(`${apiUrl}/models/active`)
    .then((r) => r.json() as Promise<{ name: string }>)
    .then((d) => d.name)
    .catch(() => 'unknown');
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
  let lastThinkingExpanded = false;

  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

  // Handle Ctrl+C gracefully
  rl.on('SIGINT', () => {
    console.log('\n再见！');
    process.exit(0);
  });

  const ask = (): Promise<string> =>
    new Promise((resolve) => {
      process.stdout.write(`${theme.primary('❯')} `);
      rl.once('line', resolve);
    });

  while (true) {
    const input = await ask();
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
        '  /model <name> 切换模型（在发送消息时生效）',
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
            for (const msg of msgs as any[]) {
              if (!msg) continue;

              const reasoning = msg.additional_kwargs?.reasoning_content as string | undefined;
              if (reasoning) {
                if (!hasThinking) { renderer.startThinking(); hasThinking = true; }
                renderer.appendThinking(reasoning);
              }

              const content = msg.content;
              if (typeof content === 'string' && content) {
                if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
                renderer.appendToken(content);
              } else if (Array.isArray(content)) {
                for (const block of content as any[]) {
                  if (block.type === 'thinking' || block.type === 'reasoning') {
                    if (!hasThinking) { renderer.startThinking(); hasThinking = true; }
                    renderer.appendThinking(block.thinking ?? block.reasoning ?? '');
                  } else if (block.type === 'text' && block.text) {
                    if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
                    renderer.appendToken(block.text);
                  }
                }
              }
            }
          }

          // updates: tool calls + HITL interrupt
          if (chunk.event === 'updates') {
            const data = chunk.data as Record<string, unknown>;

            if (data.__interrupt__) {
              if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
              renderer.newline();
              const interruptValue = (data.__interrupt__ as any[])[0]?.value as InterruptPayload;
              await handleHITL(interruptValue, client, renderer, threadId!);
              streamInput = null; // resume
              interrupted = true;
              break;
            }
          }

          // tasks: alternative HITL signal
          if (chunk.event === 'tasks') {
            const task = chunk.data as any;
            if (task?.interrupts?.length > 0) {
              if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
              renderer.newline();
              const interruptValue = task.interrupts[0]?.value as InterruptPayload;
              await handleHITL(interruptValue, client, renderer, threadId!);
              streamInput = null;
              interrupted = true;
              break;
            }
          }

          // skill suggestion
          if (chunk.event === 'skill_suggestion') {
            const s = chunk.data as any;
            renderer.skillSuggestion(s.category, s.name, s.description);
            const rl2 = readline.createInterface({ input: process.stdin, output: process.stdout });
            const ans = await new Promise<string>((r) => rl2.question('❯ ', r));
            rl2.close();
            if (ans.trim().toLowerCase() === 'y') {
              await client.acceptSkillSuggestion(threadId!).catch(() => {});
              renderer.success('技能已保存');
            } else {
              await client.dismissSkillSuggestion(threadId!).catch(() => {});
            }
          }

          // error
          if (chunk.event === 'error') {
            renderer.error((chunk.data as any)?.message ?? '未知错误');
          }
        }

        if (hasThinking && !thinkingEnded) { renderer.endThinking(); }

        if (!interrupted) break;
        interrupted = false;
        // continue while loop with streamInput = null (resume)

      } catch (e) {
        renderer.error(`流式错误: ${(e as Error).message}`);
        break;
      }
    }

    renderer.newline();
  }
}
```

- [ ] **Step 2: Wire placeholder for commands/run.ts so index.ts compiles**

```ts
// cli/src/commands/run.ts (temporary stub)
export async function runCommand(message: string): Promise<void> {
  console.log(`run: ${message} (not yet implemented)`);
}
```

- [ ] **Step 3: Verify CLI starts**

Make sure the backend is running (`cd backend && uv run uvicorn choreo.gateway.app:app --reload`), then:

```bash
cd cli && npx tsx src/index.ts --help
```

Expected: help text with `run` command listed.

- [ ] **Step 4: Smoke test interactive mode**

```bash
cd cli && npx tsx src/index.ts
```

Expected: wizard appears (first run) or REPL prompt `❯` appears directly.

- [ ] **Step 5: Commit**

```bash
git add cli/src/commands/chat.ts cli/src/commands/run.ts
git commit -m "feat(cli): interactive REPL chat command with streaming + HITL"
```

---

## Task 9: Run Command (Single-Shot)

**Files:**
- Modify: `cli/src/commands/run.ts`

- [ ] **Step 1: Replace stub with full implementation**

```ts
// cli/src/commands/run.ts
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

    for await (const chunk of streamRun(config.apiUrl, threadId, streamInput)) {
      if (chunk.event === 'messages') {
        const msgs = Array.isArray(chunk.data) ? chunk.data : [chunk.data];
        for (const msg of msgs as any[]) {
          if (!msg) continue;
          const reasoning = msg.additional_kwargs?.reasoning_content as string | undefined;
          if (reasoning) {
            if (!hasThinking) { renderer.startThinking(); hasThinking = true; }
            renderer.appendThinking(reasoning);
          }
          const content = msg.content;
          if (typeof content === 'string' && content) {
            if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
            renderer.appendToken(content);
          } else if (Array.isArray(content)) {
            for (const block of content as any[]) {
              if (block.type === 'thinking' || block.type === 'reasoning') {
                if (!hasThinking) { renderer.startThinking(); hasThinking = true; }
                renderer.appendThinking(block.thinking ?? block.reasoning ?? '');
              } else if (block.type === 'text' && block.text) {
                if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
                renderer.appendToken(block.text);
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
          const interruptValue = (data.__interrupt__ as any[])[0]?.value as InterruptPayload;
          await handleHITL(interruptValue, client, renderer, threadId);
          streamInput = null;
          interrupted = true;
          break;
        }
      }

      if (chunk.event === 'tasks') {
        const task = chunk.data as any;
        if (task?.interrupts?.length > 0) {
          if (hasThinking && !thinkingEnded) { renderer.endThinking(); thinkingEnded = true; }
          renderer.newline();
          const interruptValue = task.interrupts[0]?.value as InterruptPayload;
          await handleHITL(interruptValue, client, renderer, threadId);
          streamInput = null;
          interrupted = true;
          break;
        }
      }

      if (chunk.event === 'error') {
        renderer.error((chunk.data as any)?.message ?? '未知错误');
      }
    }

    if (hasThinking && !thinkingEnded) renderer.endThinking();
    if (!interrupted) break;
  }

  renderer.newline();
  process.exit(0);
}
```

- [ ] **Step 2: Run all tests**

```bash
cd cli && npx vitest run
```

Expected: all tests pass.

- [ ] **Step 3: Smoke test run command**

With backend running:

```bash
cd cli && npx tsx src/index.ts run "列出当前目录的文件"
```

Expected: AI streams a response, then process exits automatically.

- [ ] **Step 4: Final commit**

```bash
git add cli/src/commands/run.ts
git commit -m "feat(cli): single-shot run command — streams response then exits"
```

---

## Verification Checklist

- [ ] `cd cli && npx tsx src/index.ts --help` → shows help
- [ ] First run: wizard appears, saves `~/.choreo/config.json`
- [ ] Subsequent runs: no wizard, straight to REPL
- [ ] Type a question → see thinking block fold → AI response streams
- [ ] Trigger bash tool → see tool box + `[y/n/e]` prompt → `y` continues
- [ ] Trigger `rm -rf` → red danger box appears
- [ ] `CHOREO_API_URL=http://other:8000 npx tsx src/index.ts` → connects to alternate backend
- [ ] `npx tsx src/index.ts run "say hello"` → streams output and exits
- [ ] `/new` creates new thread, `/config` re-runs wizard, `/quit` exits
