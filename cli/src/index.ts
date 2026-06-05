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
