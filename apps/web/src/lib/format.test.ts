import { describe, expect, it } from "vitest";

import { formatBytes, metricDeltas, titleCase, usedFraction } from "./format";
import type { ExperimentRecord, MetricSpec, MetricValue } from "./types";

const SPECS: MetricSpec[] = [
  { key: "tokens_per_second", name: "Throughput", kind: "performance", higher_is_better: true, unit: null, applies_to: [] },
  { key: "peak_memory_bytes", name: "Peak memory", kind: "performance", higher_is_better: false, unit: null, applies_to: [] },
];

function experiment(baseline: MetricValue[] | null, optimized: MetricValue[] | null): ExperimentRecord {
  const result = (metrics: MetricValue[] | null) =>
    metrics && { modality: "text" as const, task: "chat", methodology: "test", metrics, simulated: false };
  return {
    id: "exp",
    name: "Experiment",
    model: { id: "m", revision: null },
    backend: "mock",
    baseline: result(baseline),
    optimized: result(optimized),
    started_at: "2026-01-01T00:00:00Z",
    finished_at: null,
  };
}

const metric = (key: string, value: number): MetricValue => ({ key, value, unit: null });

describe("formatBytes", () => {
  it("uses decimal units and trims precision for large values", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(75_000_000)).toBe("75.0 MB");
    expect(formatBytes(19_327_352_832)).toBe("19.3 GB");
    expect(formatBytes(494_384_795_648)).toBe("494 GB");
  });

  it("shows a dash when the size is unknown", () => {
    expect(formatBytes(null)).toBe("—");
  });
});

describe("usedFraction", () => {
  it("returns the used share, clamped to 0..1", () => {
    expect(usedFraction(100, 25)).toBe(0.75);
    expect(usedFraction(0, 0)).toBe(0);
    expect(usedFraction(100, 150)).toBe(0);
  });
});

describe("titleCase", () => {
  it("turns snake_case keys into labels", () => {
    expect(titleCase("not_applicable")).toBe("Not applicable");
  });
});

describe("metricDeltas", () => {
  it("marks improvement by each metric's direction, not by sign", () => {
    const deltas = metricDeltas(
      experiment(
        [metric("tokens_per_second", 10), metric("peak_memory_bytes", 8)],
        [metric("tokens_per_second", 15), metric("peak_memory_bytes", 4)],
      ),
      SPECS,
    );

    expect(deltas).toEqual([
      { key: "tokens_per_second", name: "Throughput", change: 0.5, improved: true },
      { key: "peak_memory_bytes", name: "Peak memory", change: -0.5, improved: true },
    ]);
  });

  it("flags a regression", () => {
    const [delta] = metricDeltas(
      experiment([metric("tokens_per_second", 10)], [metric("tokens_per_second", 5)]),
      SPECS,
    );

    expect(delta?.improved).toBe(false);
  });

  it("leaves out metrics that cannot be compared", () => {
    const record = experiment(
      [metric("tokens_per_second", 0), metric("peak_memory_bytes", 8), metric("unknown", 1)],
      [metric("tokens_per_second", 5), metric("unknown", 2)],
    );

    expect(metricDeltas(record, SPECS)).toEqual([]);
  });

  it("returns nothing without both a baseline and an optimized result", () => {
    expect(metricDeltas(experiment([metric("tokens_per_second", 1)], null), SPECS)).toEqual([]);
  });
});
