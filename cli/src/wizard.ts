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
