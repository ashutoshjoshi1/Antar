import { formatCount, formatDuration, formatPercent, UNAVAILABLE } from "./format";
import type {
  BenchmarkPrompt,
  ComparisonReport,
  ComparisonRow,
  MeasuredBy,
  ModelSpec,
  RunRecord,
  Scope,
  Workload,
} from "./types";

export const SCOPE_ORDER: readonly Scope[] = ["end_to_end", "model", "quality", "reliability"];

export const SCOPE_LABELS: Record<Scope, { title: string; help: string }> = {
  end_to_end: {
    title: "End to end",
    help: "What a user waits for, including the path to the backend.",
  },
  model: { title: "Model only", help: "Inference alone, as each backend reports it." },
  quality: { title: "Quality", help: "Fixed-rule checks against reference answers." },
  reliability: { title: "Reliability", help: "Requests that failed." },
};

export const MEASURED_BY_LABELS: Record<MeasuredBy, string> = {
  antar: "Antar API",
  backend: "backend",
  scorer: "Antar scorer",
};

const ONE_MS = 1;

/** A row value in its unit. Null is "Unavailable", never zero. */
export function formatRowValue(value: number | null, unit: string | null): string {
  if (value === null) return UNAVAILABLE;
  switch (unit) {
    case "ms":
      // The mock answers in microseconds; rounding that to "0 ms" would read as a missing value.
      return value > 0 && value < ONE_MS ? `${value.toPrecision(2)} ms` : formatDuration(value);
    case "ratio":
      return formatPercent(value);
    case "tok/s":
      return formatCount(value, "tokens/s");
    default:
      return formatCount(value, unit ?? "");
  }
}

/** Workload ids that have rows, "all" first, otherwise in the order the report lists them. */
export function rowWorkloads(rows: ComparisonRow[]): string[] {
  const ids = [...new Set(rows.map((row) => row.workload))];
  return [...ids.filter((id) => id === "all"), ...ids.filter((id) => id !== "all")];
}

export interface RowGroup {
  scope: Scope;
  rows: ComparisonRow[];
}

/** One workload's rows grouped by what they measure. Scopes with no rows are left out. */
export function groupRows(rows: ComparisonRow[], workload: string): RowGroup[] {
  const mine = rows.filter((row) => row.workload === workload);
  return SCOPE_ORDER.map((scope) => ({
    scope,
    rows: mine.filter((row) => row.scope === scope),
  })).filter((group) => group.rows.length > 0);
}

export function isScored(workload: Workload): boolean {
  return workload.prompts.some((prompt) => Boolean(prompt.expect));
}

/** Auto-scored workloads have reference answers; the rest need a person to read them. */
export function splitWorkloads(workloads: Workload[]): { scored: Workload[]; manual: Workload[] } {
  return {
    scored: workloads.filter(isScored),
    manual: workloads.filter((workload) => !isScored(workload)),
  };
}

export const CODE_TESTS_WORKLOAD = "code_tests";

/** Requests a comparison sends: the same run once per side. */
export function comparisonRequestCount(
  workloads: Workload[],
  selected: readonly string[],
  warmup: number,
  runs: number,
): number {
  const perSide = workloads
    .filter((workload) => selected.includes(workload.id))
    .reduce((total, workload) => total + warmup + runs * workload.prompts.length, 0);
  return 2 * perSide;
}

const canChat = (model: ModelSpec) => model.tasks.includes("chat") && model.downloaded === true;

/**
 * Models offered for each side. Mock models are offered on both so the lab can
 * be exercised offline; a comparison that uses one is labelled simulated.
 */
export function sideCandidates(models: ModelSpec[]): { local: ModelSpec[]; cloud: ModelSpec[] } {
  const usable = models.filter(canChat);
  return {
    local: usable.filter((model) => model.location !== "cloud"),
    cloud: usable.filter((model) => model.location === "cloud" || model.simulated),
  };
}

export interface ResponsePair {
  key: string;
  workload: Workload;
  prompt: BenchmarkPrompt;
  local: RunRecord | undefined;
  cloud: RunRecord | undefined;
}

/** Each prompt with the first measured answer from either side, in workload order. */
export function pairResponses(report: ComparisonReport): ResponsePair[] {
  const source = report.local ?? report.cloud;
  if (!source) return [];
  const first = (runs: RunRecord[] | undefined, workload: string, prompt: string) =>
    runs?.find(
      (run) => run.phase === "measured" && run.workload === workload && run.prompt_id === prompt,
    );
  return source.workloads.flatMap((workload) =>
    workload.prompts.map((prompt) => ({
      key: `${workload.id}:${prompt.id}`,
      workload,
      prompt,
      local: first(report.local?.runs, workload.id, prompt.id),
      cloud: first(report.cloud?.runs, workload.id, prompt.id),
    })),
  );
}

export interface ChartMetric {
  metric: string;
  title: string;
  unit: string;
  local: number | null;
  cloud: number | null;
}

const CHART_METRICS: readonly { metric: string; title: string; unit: string }[] = [
  { metric: "latency_ms_median", title: "End-to-end latency, median", unit: "ms" },
  {
    metric: "decode_tokens_per_second_median",
    title: "Tokens per second after the first token, median",
    unit: "tokens/s",
  },
];

/** Overall rows worth drawing. A metric neither side has is left out, not drawn as zero. */
export function chartMetrics(rows: ComparisonRow[]): ChartMetric[] {
  return CHART_METRICS.flatMap((spec) => {
    const row = rows.find((item) => item.workload === "all" && item.metric === spec.metric);
    if (!row || (row.local === null && row.cloud === null)) return [];
    return [{ ...spec, local: row.local, cloud: row.cloud }];
  });
}

/** What the scorer was given to compare a response with, in words. */
export function describeExpectation(prompt: BenchmarkPrompt): string | null {
  const expect = prompt.expect;
  if (!expect) return null;
  switch (expect.method) {
    case "exact":
      return `Reference answer: ${expect.answer ?? ""}`;
    case "number":
      return `Reference number: ${expect.number ?? ""}`;
    case "keywords":
      return `Must mention: ${expect.keywords.join(", ")}`;
    case "json_fields":
      return `Must be JSON with fields: ${Object.keys(expect.fields).join(", ")}`;
    case "python_tests":
      return `Checked by ${expect.tests.length} unit test assertions`;
  }
}
