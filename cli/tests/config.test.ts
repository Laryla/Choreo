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
