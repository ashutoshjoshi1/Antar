import { Link } from "react-router";

import { LocationBadge, PageHeader, Panel, QueryView, Tag, Value } from "../components/ui";
import { API_BASE, comparisonExportUrl, useBenchmarkHistory, useComparisonHistory } from "../lib/api";
import { formatCount, formatDateTime, formatDuration, formatMoney } from "../lib/format";
import type { ComparisonSummary, ReportSummary } from "../lib/types";

const linkClass = "rounded border border-line px-2 py-1 text-xs whitespace-nowrap hover:border-muted";
const cell = "border-t border-line py-2.5 pr-4 align-top";

function StatusTags({ status, simulated }: { status: string; simulated: boolean }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      {simulated && <Tag tone="warn">Simulated</Tag>}
      {status === "completed" ? <Tag>Completed</Tag> : <Tag tone="warn">{status}</Tag>}
    </span>
  );
}

function Comparisons({ comparisons }: { comparisons: ComparisonSummary[] }) {
  if (comparisons.length === 0) {
    return (
      <p className="text-sm text-muted">
        No comparison has been saved yet. Run one in the{" "}
        <Link to="/compare" className="text-ink underline">
          Comparison Lab
        </Link>
        .
      </p>
    );
  }
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[58rem] border-separate border-spacing-0 text-sm">
        <caption className="sr-only">Saved local-versus-cloud comparisons</caption>
        <thead className="text-left text-muted">
          <tr>
            {["Comparison", "Models", "Status", "Commit"].map((heading) => (
              <th key={heading} scope="col" className="pb-2 pr-4 font-normal">
                {heading}
              </th>
            ))}
            <th scope="col" className="pb-2 pr-4 text-right font-normal">Estimated cost</th>
            <th scope="col" className="pb-2 pr-4 font-normal">Started</th>
            <th scope="col" className="pb-2 font-normal">Open and export</th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((item) => (
            <tr key={item.id} className="hover:bg-raised/30">
              <td className={cell}>
                <Link to={`/compare?report=${item.id}`} className="break-words underline decoration-line underline-offset-4 hover:decoration-ink">
                  {item.name}
                </Link>
                <span className="mt-0.5 block text-2xs text-faint">{item.workloads.join(", ")}</span>
              </td>
              <td className={cell}>
                <span className="flex items-center gap-2">
                  <LocationBadge location="local" />
                  <span className="font-mono text-xs break-all">{item.local_model}</span>
                </span>
                <span className="mt-1 flex items-center gap-2">
                  <LocationBadge location="cloud" />
                  <span className="font-mono text-xs break-all">{item.cloud_model}</span>
                </span>
              </td>
              <td className={cell}>
                <StatusTags status={item.status} simulated={item.simulated} />
              </td>
              <td className={`${cell} font-mono text-xs`}>{item.git_commit ?? <span className="text-faint">Not recorded</span>}</td>
              <td className={`${cell} tabular text-right`}>
                <Value>{formatMoney(item.estimated_cost_usd)}</Value>
              </td>
              <td className={`${cell} text-muted`}>
                {formatDateTime(item.started_at)}
                <span className="block text-2xs text-faint">Finished {formatDateTime(item.finished_at)}</span>
              </td>
              <td className="border-t border-line py-2.5 align-top">
                <span className="flex flex-wrap gap-1.5">
                  <Link to={`/compare?report=${item.id}`} className={linkClass} aria-label={`Open report ${item.name}`}>
                    Open
                  </Link>
                  {(["json", "csv", "md"] as const).map((format) => (
                    <a key={format} className={linkClass} href={comparisonExportUrl(item.id, format)} download aria-label={`Export ${item.name} as ${format}`}>
                      {format === "md" ? "Markdown" : format.toUpperCase()}
                    </a>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Benchmarks({ reports }: { reports: ReportSummary[] }) {
  if (reports.length === 0) {
    return (
      <p className="text-sm text-muted">
        No benchmark has been saved yet. Run one on the{" "}
        <Link to="/benchmarks" className="text-ink underline">
          Benchmarks
        </Link>{" "}
        page.
      </p>
    );
  }
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full min-w-[50rem] border-separate border-spacing-0 text-sm">
        <caption className="sr-only">Saved single-backend benchmarks</caption>
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="pb-2 pr-4 font-normal">Benchmark</th>
            <th scope="col" className="pb-2 pr-4 font-normal">Status</th>
            <th scope="col" className="pb-2 pr-4 text-right font-normal">Median latency</th>
            <th scope="col" className="pb-2 pr-4 text-right font-normal">Median tokens/s</th>
            <th scope="col" className="pb-2 pr-4 font-normal">Started</th>
            <th scope="col" className="pb-2 font-normal">Open and export</th>
          </tr>
        </thead>
        <tbody>
          {reports.map((report) => (
            <tr key={report.id} className="hover:bg-raised/30">
              <td className={cell}>
                <Link to={`/benchmarks?report=${report.id}`} className="font-mono text-[0.8125rem] break-all underline decoration-line underline-offset-4 hover:decoration-ink">
                  {report.model}
                </Link>
                <span className="mt-0.5 block text-2xs text-faint">
                  {report.backend}
                  {report.quantization ? `, ${report.quantization}` : ""} · {report.workloads.join(", ")}
                </span>
              </td>
              <td className={cell}>
                <StatusTags status={report.status} simulated={report.simulated} />
              </td>
              <td className={`${cell} tabular text-right`}>
                <Value>{formatDuration(report.overall?.latency_ms_median)}</Value>
              </td>
              <td className={`${cell} tabular text-right`}>
                <Value>{formatCount(report.overall?.tokens_per_second_median)}</Value>
              </td>
              <td className={`${cell} text-muted`}>{formatDateTime(report.started_at)}</td>
              <td className="border-t border-line py-2.5 align-top">
                <span className="flex flex-wrap gap-1.5">
                  <Link to={`/benchmarks?report=${report.id}`} className={linkClass} aria-label={`Open benchmark ${report.id}`}>
                    Open
                  </Link>
                  {(["json", "csv"] as const).map((format) => (
                    <a key={format} className={linkClass} href={`${API_BASE}/api/v1/benchmarks/${report.id}/export?format=${format}`} download>
                      {format.toUpperCase()}
                    </a>
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function History() {
  const comparisons = useComparisonHistory();
  const benchmarks = useBenchmarkHistory();
  return (
    <>
      <PageHeader
        title="Experiment History"
        summary="Every saved comparison and benchmark, newest first. Each opens to its full report with the settings, versions, and commit it ran with."
      />
      <div className="space-y-6">
        <Panel title="Local versus cloud comparisons" aside={<span className="text-xs text-faint">Latency and scores are in each report</span>}>
          <QueryView query={comparisons}>{(items) => <Comparisons comparisons={items} />}</QueryView>
        </Panel>
        <Panel title="Single-backend benchmarks" aside={<span className="text-xs text-faint">Latency measured by the Antar API; tokens/s reported by the backend</span>}>
          <QueryView query={benchmarks}>{(items) => <Benchmarks reports={items} />}</QueryView>
        </Panel>
      </div>
    </>
  );
}
