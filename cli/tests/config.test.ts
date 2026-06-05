import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { tmpdir } from 'os';
import { join } from 'path';
import { writeFileSync, mkdirSync, rmSync } from 'fs';

const tmpHome = join(tmpdir(), `choreo-test-${Date.now()}`);

beforeEach(() => {
  mkdirSync(tmpHome, { recursive: true });
  vi.resetModules();
});
afterEach(() => {
  rmSync(tmpHome, { recursive: true, force: true });
  delete process.env.HOME;
});

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
    const { loadConfig } = await import('../src/config.js');
    const cfg = loadConfig();
    expect(cfg.theme).toBe('#f43f5e');
    expect(cfg.apiUrl).toBe('http://localhost:8000');
  });
});

describe('configExists', () => {
  it('returns false when file missing', async () => {
    process.env.HOME = tmpHome;
    const { configExists } = await import('../src/config.js');
    expect(configExists()).toBe(false);
  });
});

describe('saveConfig', () => {
  it('writes config and can be read back', async () => {
    process.env.HOME = tmpHome;
    const { saveConfig, loadConfig } = await import('../src/config.js');
    saveConfig({ apiUrl: 'http://custom:9000', theme: '#10b981' });
    vi.resetModules();
    const { loadConfig: reload } = await import('../src/config.js');
    const cfg = reload();
    expect(cfg.apiUrl).toBe('http://custom:9000');
    expect(cfg.theme).toBe('#10b981');
  });
});
