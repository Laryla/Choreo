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
    } else {
      decision = { type: 'reject' };
    }

    await client.submitState(threadId, [decision]);
  }

  rl.close();
}
