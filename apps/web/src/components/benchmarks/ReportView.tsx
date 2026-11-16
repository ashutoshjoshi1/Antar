import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { API_BASE, useBenchmarkReport, useEvaluateRun } from "../../lib/api";
import { comparisonIssues } from "../../lib/benchmarks";
import { formatBytes, formatCount, formatDuration, formatPercent } from "../../lib/format";
import type { Aggregate, BenchmarkReport, ReportSummary, RunRecord } from "../../lib/types";
import { Fact, Panel, QueryView, Tag } from "../ui";

const axis = { stroke: "var(--color-faint)", tick: { fill: "var(--color-muted)", fontSize: 12 } };
const tooltipStyle = {
  background: "var(--color-ground)",
  border: "1px solid var(--color-line)",
  borderRadius: 6,
  fontSize: 12,
};

function AggregateTable({ report }: { report: BenchmarkReport }) {
  const name = (aggregate: Aggregate) =>
    aggregate.workload === "all"
      ? "All workloads"
      : (report.workloads.find((workload) => workload.id === aggregate.workload)?.name ?? aggregate.workload);
  const showJson = report.aggregates.some((aggregate) => aggregate.json_valid_rate !== null);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] border-separate border-spacing-0 text-sm">
        <caption className="sr-only">Statistics over measured requests</caption>
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="pb-2 font-normal">Workload</th>
            {["Completed", "Errors", "Latency mean", "Median", "P95", "Tokens/s mean", "Median"].map((heading, index) => (
              <th key={`${heading}-${index}`} scope="col" className="pb-2 text-right font-normal">
                {heading}
              </th>
            ))}
            {showJson && <th scope="col" className="pb-2 text-right font-normal">Valid JSON</th>}
          </tr>
        </thead>
        <tbody className="tabular">
          {report.aggregates.map((aggregate) => (
            <tr key={aggregate.workload} className={aggregate.workload === "all" ? "font-medium" : ""}>
              <th scope="row" className="border-t border-line py-2 pr-4 text-left font-[inherit]">
                {name(aggregate)}
              </th>
              <td className="border-t border-line py-2 text-right">{aggregate.completed}</td>
              <td className={`border-t border-line py-2 text-right ${aggregate.failed ? "text-down" : ""}`}>
                {formatPercent(aggregate.error_rate)}
              </td>
              <td className="border-t border-line py-2 text-right">{formatDuration(aggregate.latency_ms_mean)}</td>
              <td className="border-t border-line py-2 text-right">{formatDuration(aggregate.latency_ms_median)}</td>
              <td className="border-t border-line py-2 text-right">{formatDuration(aggregate.latency_ms_p95)}</td>
              <td className="border-t border-line py-2 text-right">{formatCount(aggregate.tokens_per_second_mean)}</td>
              <td className="border-t border-line py-2 text-right">{formatCount(aggregate.tokens_per_second_median)}</td>
              {showJson && (
                <td className="border-t border-line py-2 text-right">
                  {aggregate.json_valid_rate === null ? "—" : formatPercent(aggregate.json_valid_rate)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RunCharts({ runs }: { runs: RunRecord[] }) {
  const measured = runs
    .filter((run) => run.phase === "measured" && run.metrics)
    .map((run, order) => ({
      label: `${order + 1}`,
      prompt: run.prompt_id,
      latency: run.metrics ? Math.round(run.metrics.latency_ms) : null,
      speed: run.metrics?.tokens_per_second ?? null,
    }));
  if (measured.length === 0) return null;
  const hasSpeed = measured.some((run) => run.speed !== null);
  return (
    <div className="grid gap-6 lg:grid-cols-2" aria-hidden>
      <figure>
        <figcaption className="mb-2 text-sm text-muted">Latency of each measured request, ms</figcaption>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={measured} margin={{ left: -8, right: 8 }}>
            <CartesianGrid stroke="var(--color-line)" vertical={false} />
            <XAxis dataKey="label" {...axis} />
            <YAxis {...axis} />
            <Tooltip cursor={{ fill: "var(--color-raised)" }} contentStyle={tooltipStyle} labelFormatter={(_, items) => String(items[0]?.payload?.prompt ?? "")} />
            <Bar dataKey="latency" name="Latency (ms)" radius={2} isAnimationActive={false}>
              {measured.map((run) => (
                <Cell key={run.label} fill="var(--color-ink)" fillOpacity={0.7} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </figure>
      {hasSpeed && (
        <figure>
          <figcaption className="mb-2 text-sm text-muted">Generation speed of each measured request, tokens/s</figcaption>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={measured} margin={{ left: -8, right: 8 }}>
              <CartesianGrid stroke="var(--color-line)" vertical={false} />
              <XAxis dataKey="label" {...axis} />
              <YAxis {...axis} />
              <Tooltip cursor={{ fill: "var(--color-raised)" }} contentStyle={tooltipStyle} labelFormatter={(_, items) => String(items[0]?.payload?.prompt ?? "")} formatter={(value) => Number(value).toFixed(1)} />
              <Bar dataKey="speed" name="Tokens/s" fill="var(--color-local)" radius={2} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </figure>
      )}
    </div>
  );
}

function ManualReview({ report, run }: { report: BenchmarkReport; run: RunRecord }) {
  const evaluate = useEvaluateRun();
  const [notes, setNotes] = useState(run.manual_notes ?? "");
  const save = (score: number | null) =>
    evaluate.mutate({ reportId: report.id, runIndex: run.index, score, notes: notes.trim() || null });
  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
      <label className="flex items-center gap-2">
        Your score
        <select
          className="rounded-md border border-line bg-ground px-2 py-1"
          value={run.manual_score ?? ""}
          onChange={(event) => save(event.target.value ? Number(event.target.value) : null)}
        >
          <option value="">Not reviewed</option>
          {[1, 2, 3, 4, 5].map((score) => (
            <option key={score} value={score}>
              {score}
            </option>
          ))}
        </select>
      </label>
      <input
        aria-label="Review notes"
        placeholder="Notes"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        onBlur={() => notes !== (run.manual_notes ?? "") && save(run.manual_score)}
        className="min-w-48 flex-1 rounded-md border border-line bg-ground px-2 py-1 placeholder:text-faint"
      />
      {evaluate.isError && <span className="text-down">{evaluate.error.message}</span>}
    </div>
  );
}

function Responses({ report }: { report: BenchmarkReport }) {
  const runs = report.runs.filter((run) => run.phase === "measured");
  const prompt = (run: RunRecord) =>
    report.workloads.find((workload) => workload.id === run.workload)?.prompts.find((item) => item.id === run.prompt_id);
  return (
    <details>
      <summary className="cursor-pointer text-sm select-none">
        Responses and manual review ({runs.length})
      </summary>
      <p className="mt-2 max-w-[75ch] text-xs text-muted">
        Antar does not score free-text or image answers. Read them and record your own judgement;
        it is saved with the report.
      </p>
      <ol className="mt-3 space-y-4">
        {runs.map((run) => (
          <li key={run.index} className="rounded-md border border-line bg-ground/50 p-3">
            <p className="text-xs text-muted">
              {prompt(run)?.text ?? run.prompt_id}
              {prompt(run)?.image && <span className="text-faint"> (image: {prompt(run)?.image})</span>}
            </p>
            {run.ok ? (
              <p className="mt-2 max-h-48 overflow-y-auto text-sm whitespace-pre-wrap">{run.response}</p>
            ) : (
              <p className="mt-2 text-sm text-down">{run.error}</p>
            )}
            {run.json_valid !== null && (
              <p className="mt-2">
                <Tag tone={run.json_valid ? "plain" : "warn"}>{run.json_valid ? "Valid JSON" : "Not valid JSON"}</Tag>
              </p>
            )}
            {run.ok && <ManualReview report={report} run={run} />}
          </li>
        ))}
      </ol>
    </details>
  );
}

function Comparison({ report, others }: { report: BenchmarkReport; others: ReportSummary[] }) {
  const [otherId, setOtherId] = useState<string | null>(null);
  const other = useBenchmarkReport(otherId);
  const overall = (item: BenchmarkReport) => item.aggregates.find((aggregate) => aggregate.workload === "all");
  if (others.length === 0) return null;
  const issues = other.data ? comparisonIssues(report, other.data) : [];
  const rows = other.data
    ? ([
        ["Median latency", formatDuration(overall(report)?.latency_ms_median), formatDuration(overall(other.data)?.latency_ms_median)],
        ["P95 latency", formatDuration(overall(report)?.latency_ms_p95), formatDuration(overall(other.data)?.latency_ms_p95)],
        ["Median tokens/s", formatCount(overall(report)?.tokens_per_second_median), formatCount(overall(other.data)?.tokens_per_second_median)],
        ["Error rate", formatPercent(overall(report)?.error_rate), formatPercent(overall(other.data)?.error_rate)],
      ] as const)
    : [];
  return (
    <div>
      <label className="flex flex-wrap items-center gap-2 text-sm">
        Compare with
        <select className="rounded-md border border-line bg-ground px-2 py-1" value={otherId ?? ""} onChange={(event) => setOtherId(event.target.value || null)}>
          <option value="">Choose a report</option>
          {others.map((item) => (
            <option key={item.id} value={item.id}>
              {item.model} {item.quantization ?? ""} ({new Date(item.started_at).toLocaleString()})
            </option>
          ))}
        </select>
      </label>
      {other.data && (
        <>
          {issues.length > 0 && (
            <div role="note" className="mt-3 rounded-md border border-warn/50 bg-warn/5 px-3 py-2 text-sm">
              <p className="text-warn">These two runs are not directly comparable</p>
              <ul className="mt-1 list-disc pl-5 text-muted">
                {issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </div>
          )}
          <table className="tabular mt-3 w-full max-w-xl text-sm">
            <thead className="text-left text-muted">
              <tr>
                <th scope="col" className="pb-1 font-normal">Measured runs</th>
                <th scope="col" className="pb-1 text-right font-normal">{report.model.id}</th>
                <th scope="col" className="pb-1 text-right font-normal">{other.data.model.id}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(([label, mine, theirs]) => (
                <tr key={label}>
                  <th scope="row" className="border-t border-line py-1.5 text-left font-normal">{label}</th>
                  <td className="border-t border-line py-1.5 text-right">{mine}</td>
                  <td className="border-t border-line py-1.5 text-right">{theirs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

function Report({ report, others }: { report: BenchmarkReport; others: ReportSummary[] }) {
  const exportUrl = (format: "json" | "csv") => `${API_BASE}/api/v1/benchmarks/${report.id}/export?format=${format}`;
  const linkClass = "rounded-md border border-line px-3 py-1.5 text-sm hover:border-muted";
  return (
    <Panel
      title={report.config.name}
      aside={
        <span className="flex items-center gap-2">
          {report.simulated && <Tag tone="warn">Simulated, not a real result</Tag>}
          {report.status !== "completed" && <Tag tone="warn">{report.status}</Tag>}
          <span className="font-mono text-xs text-faint">{report.id}</span>
        </span>
      }
    >
      <div className="space-y-6">
        {report.failure && (
          <p role="alert" className="rounded-md border border-down/50 bg-down/5 px-3 py-2 text-sm text-down">
            {report.failure}
          </p>
        )}
        <AggregateTable report={report} />
        <p className="text-xs text-faint">
          Statistics cover measured requests only; warm-up and cold requests are excluded. P95 is the
          nearest-rank percentile. Latency is measured by the Antar API; tokens per second is reported
          by Lemonade for each response.
        </p>
        <RunCharts runs={report.runs} />

        {report.cold_start && (
          <dl className="max-w-md">
            <Fact term="Model load time">{formatDuration(report.cold_start.load_time_ms)}</Fact>
            <Fact term="First request after loading">
              {formatDuration(report.cold_start.first_request?.metrics?.latency_ms)}
            </Fact>
          </dl>
        )}

        <div className="grid gap-x-10 gap-y-6 lg:grid-cols-2">
          <dl>
            <Fact term="Model">
              <span className="font-mono text-xs">{report.model.checkpoint ?? report.model.id}</span>
            </Fact>
            <Fact term="Quantization">{report.model.quantization ?? "Not stated"}</Fact>
            <Fact term="Size">{formatBytes(report.model.size_bytes)}</Fact>
            <Fact term="Runtime">
              {report.backend} {report.backend_version ?? ""}, {report.model.runtime ?? "runtime not stated"}
            </Fact>
            <Fact term="Hardware">
              {report.hardware.cpu_model}, {formatBytes(report.hardware.memory_total_bytes)}
            </Fact>
            <Fact term="System">
              {report.hardware.os} {report.hardware.os_version}
            </Fact>
          </dl>
          <dl>
            <Fact term="Settings">
              {report.config.max_tokens} tokens, temperature {report.config.temperature}, seed {report.config.seed ?? "none"}
            </Fact>
            <Fact term="Warm-up, measured passes">
              {report.config.warmup_runs}, {report.config.measured_runs}
            </Fact>
            <Fact term="Started">{new Date(report.started_at).toLocaleString()}</Fact>
            <Fact term="Antar">
              {report.antar_version}
              {report.git_commit ? ` (${report.git_commit})` : ""}
            </Fact>
          </dl>
        </div>

        {report.missing_telemetry.length > 0 && (
          <details>
            <summary className="cursor-pointer text-sm select-none">
              Not measured ({report.missing_telemetry.length})
            </summary>
            <ul className="mt-2 space-y-1 text-sm text-muted">
              {report.missing_telemetry.map((item) => (
                <li key={item.metric}>
                  <span className="font-mono text-xs text-ink">{item.metric}</span>: {item.reason}
                </li>
              ))}
            </ul>
          </details>
        )}

        <Responses report={report} />
        <Comparison report={report} others={others} />

        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          <a className={linkClass} href={exportUrl("json")} download>
            Export JSON
          </a>
          <a className={linkClass} href={exportUrl("csv")} download>
            Export CSV
          </a>
        </div>
      </div>
    </Panel>
  );
}

export function ReportView({ id, history }: { id: string; history: ReportSummary[] }) {
  const report = useBenchmarkReport(id);
  return (
    <QueryView query={report}>
      {(data) => <Report report={data} others={history.filter((item) => item.id !== id)} />}
    </QueryView>
  );
}
