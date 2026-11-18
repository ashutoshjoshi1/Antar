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

/** How a value the source did not report is shown. Never a zero. */
export const UNAVAILABLE = "Unavailable";

/** Milliseconds as ms below one second, otherwise seconds. */
export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return UNAVAILABLE;
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

export function formatCount(value: number | null | undefined, unit = ""): string {
  if (value === null || value === undefined) return UNAVAILABLE;
  const digits = Number.isInteger(value) ? 0 : 1;
  return `${value.toLocaleString("en-US", { maximumFractionDigits: digits })}${unit && ` ${unit}`}`;
}

export function formatPercent(fraction: number | null | undefined): string {
  if (fraction === null || fraction === undefined) return UNAVAILABLE;
  return `${(fraction * 100).toFixed(fraction > 0 && fraction < 0.1 ? 1 : 0)}%`;
}

export function formatMoney(usd: number | null | undefined): string {
  if (usd === null || usd === undefined) return UNAVAILABLE;
  const digits = Math.abs(usd) > 0 && Math.abs(usd) < 1 ? 4 : 2;
  return `$${usd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: digits })}`;
}

const PARAMETER_UNITS = [
  [1e12, "T"],
  [1e9, "B"],
  [1e6, "M"],
  [1e3, "K"],
] as const;

/** A published parameter count, e.g. 8.2B. Null stays null: sizes are never guessed. */
export function formatParameters(count: number | null): string | null {
  if (count === null) return null;
  for (const [step, suffix] of PARAMETER_UNITS) {
    if (count >= step) {
      const value = count / step;
      return `${value.toFixed(value >= 100 ? 0 : 1)}${suffix}`;
    }
  }
  return String(count);
}

/** Whole seconds as h, m, s. Two-digit minutes and seconds keep a ticking value from jumping. */
export function formatElapsed(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return UNAVAILABLE;
  const total = Math.max(0, Math.floor(seconds));
  const pad = (value: number) => String(value).padStart(2, "0");
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  return hours > 0
    ? `${hours} h ${pad(minutes)} m ${pad(total % 60)} s`
    : `${minutes} m ${pad(total % 60)} s`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString();
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
