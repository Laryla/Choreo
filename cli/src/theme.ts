import chalk from 'chalk';

export interface Theme {
  primary:  (t: string) => string;
  dim:      (t: string) => string;
  success:  (t: string) => string;
  error:    (t: string) => string;
  warning:  (t: string) => string;
  cyan:     (t: string) => string;
  thinking: (t: string) => string;
  danger:   (t: string) => string;
}

export function createTheme(hexColor: string): Theme {
  return {
    primary:  (t) => chalk.hex(hexColor)(t),
    dim:      (t) => chalk.hex('#475569')(t),
    success:  (t) => chalk.hex('#4ade80')(t),
    error:    (t) => chalk.hex('#f87171')(t),
    warning:  (t) => chalk.hex('#fbbf24')(t),
    cyan:     (t) => chalk.hex('#67e8f9')(t),
    thinking: (t) => chalk.hex('#334155')(t),
    danger:   (t) => chalk.hex('#f43f5e')(t),
  };
}
