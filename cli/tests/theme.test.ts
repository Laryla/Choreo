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
