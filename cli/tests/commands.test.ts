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
