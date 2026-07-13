export const DIMENSION_LABELS: Record<string, string> = {
  functional: "功能正确性",
  process: "过程质量",
  efficiency: "效率成本",
  robustness: "鲁棒安全",
  alignment: "体验对齐",
};

export const DIMENSION_MAX: Record<string, number> = {
  functional: 30,
  process: 25,
  efficiency: 15,
  robustness: 20,
  alignment: 10,
};

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatScore(value: number): string {
  return (value * 100).toFixed(1);
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value);
}

export function formatDuration(seconds: number): string {
  return seconds < 1 ? `${Math.round(seconds * 1000)} ms` : `${seconds.toFixed(2)} s`;
}

export function formatCost(value: number): string {
  return `$${value.toFixed(4)}`;
}

export function scoreColor(value: number): string {
  if (value >= 0.8) return "var(--apple-success)";
  if (value >= 0.5) return "var(--apple-warning)";
  return "var(--apple-error)";
}

export function difficultyColor(difficulty: string): string {
  if (difficulty === "easy") return "var(--apple-success)";
  if (difficulty === "medium") return "var(--apple-warning)";
  return "var(--apple-error)";
}
