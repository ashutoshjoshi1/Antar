import type { ExperimentRecord, MetricSpec } from "./types";

const BYTE_UNITS = ["B", "KB", "MB", "GB", "TB"] as const;
const BYTES_PER_STEP = 1000;

/** Decimal (SI) units, matching how model sizes are published. */
export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  let value = bytes;
  let unit = 0;
  while (value >= BYTES_PER_STEP && unit < BYTE_UNITS.length - 1) {
    value /= BYTES_PER_STEP;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${BYTE_UNITS[unit]}`;
}

export function usedFraction(total: number, free: number): number {
  if (total <= 0) return 0;
  return Math.min(1, Math.max(0, (total - free) / total));
}

export function titleCase(value: string): string {
  const spaced = value.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export interface MetricDelta {
  key: string;
  name: string;
  /** Relative change from baseline, e.g. -0.25 for a 25% decrease. */
  change: number;
  improved: boolean;
}

/**
 * Relative change per metric between an experiment's baseline and optimized
 * results. Only metrics measured in both, with a non-zero baseline and a known
 * direction, are comparable; everything else is left out rather than guessed.
 */
export function metricDeltas(experiment: ExperimentRecord, specs: MetricSpec[]): MetricDelta[] {
  const { baseline, optimized } = experiment;
  if (!baseline || !optimized) return [];

  const after = new Map(optimized.metrics.map((metric) => [metric.key, metric.value]));
  return baseline.metrics.flatMap((before) => {
    const value = after.get(before.key);
    const spec = specs.find((candidate) => candidate.key === before.key);
    if (value === undefined || !spec || before.value === 0) return [];
    const change = (value - before.value) / Math.abs(before.value);
    return [
      {
        key: before.key,
        name: spec.name,
        change,
        improved: spec.higher_is_better ? change > 0 : change < 0,
      },
    ];
  });
}
