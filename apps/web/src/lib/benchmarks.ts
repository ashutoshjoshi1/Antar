import type { BenchmarkReport } from "./types";

const SETTINGS = ["max_tokens", "temperature", "seed", "enable_thinking"] as const;

/**
 * Reasons two reports should not be compared directly. Empty means the same
 * prompts were sent with the same generation settings.
 */
export function comparisonIssues(a: BenchmarkReport, b: BenchmarkReport): string[] {
  const issues: string[] = [];
  const version = (report: BenchmarkReport) =>
    report.workloads.map((workload) => `${workload.id}@${workload.version}`).sort().join(", ");
  if (version(a) !== version(b)) {
    issues.push(`Different workloads: ${version(a)} versus ${version(b)}.`);
  }
  for (const key of SETTINGS) {
    if (a.config[key] !== b.config[key]) {
      issues.push(`Different ${key.replaceAll("_", " ")}: ${String(a.config[key])} versus ${String(b.config[key])}.`);
    }
  }
  if (a.hardware.cpu_model !== b.hardware.cpu_model) {
    issues.push(`Different hardware: ${a.hardware.cpu_model} versus ${b.hardware.cpu_model}.`);
  }
  if (a.simulated || b.simulated) issues.push("At least one report is simulated, not measured.");
  if (a.status !== "completed" || b.status !== "completed") {
    issues.push("At least one run did not complete.");
  }
  return issues;
}
