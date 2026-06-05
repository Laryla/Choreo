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
