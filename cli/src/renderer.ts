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
