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
