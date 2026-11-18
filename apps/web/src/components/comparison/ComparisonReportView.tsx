import { lazy, Suspense } from "react";

import { comparisonExportUrl, useComparison } from "../../lib/api";
import type { ExportFormat } from "../../lib/api";
import { chartMetrics, formatRowValue } from "../../lib/comparison";
import type { ComparisonReport } from "../../lib/types";
import { buttonClass, Notice, Panel, QueryView, Tag } from "../ui";
import { CloudSideDetails, ModelFacts, Reproducibility } from "./ReportDetails";
import { ResponseViewer } from "./ResponseViewer";
import { ResultsTable } from "./ResultsTable";

// Recharts is only needed when a report has something to draw.
const ComparisonChart = lazy(() => import("./ComparisonChart"));

const EXPORTS: readonly { format: ExportFormat; label: string }[] = [
  { format: "json", label: "Export JSON" },
  { format: "csv", label: "Export CSV" },
  { format: "md", label: "Export Markdown" },
];

function Charts({ report }: { report: ComparisonReport }) {
  const metrics = chartMetrics(report.rows);
  if (metrics.length === 0) return null;
  return (
    <Suspense fallback={<p className="text-sm text-muted">Loading chart…</p>}>
      <div className="grid gap-6 lg:grid-cols-2">
        {metrics.map((metric) => (
          <figure key={metric.metric}>
            <figcaption className="mb-2 text-sm text-muted">
              {metric.title}, {metric.unit}
              {report.simulated && " (simulated)"}
            </figcaption>
            <div aria-hidden>
              <ComparisonChart metric={metric} />
            </div>
            <p className="sr-only">
              Local {formatRowValue(metric.local, metric.unit === "ms" ? "ms" : "tok/s")}, cloud{" "}
              {formatRowValue(metric.cloud, metric.unit === "ms" ? "ms" : "tok/s")}.
            </p>
          </figure>
        ))}
      </div>
      <p className="text-xs text-faint">
        Both measured by the Antar API on its own clock, the same way for each side. A side with no
        value has no bar.
      </p>
    </Suspense>
  );
}

function Report({ report }: { report: ComparisonReport }) {
  const [headline, ...otherCaveats] = report.caveats;
  const workloads = (report.local ?? report.cloud)?.workloads ?? [];
  return (
    <Panel
      title={report.config.name}
      aside={
        <span className="flex flex-wrap items-center justify-end gap-2">
          {report.simulated && <Tag tone="warn">Simulated, not a real result</Tag>}
          {report.status !== "completed" && <Tag tone="warn">{report.status}</Tag>}
          <span className="font-mono text-xs text-faint">{report.id}</span>
        </span>
      }
    >
      <div className="space-y-6">
        <Notice title="Not a hardware-normalized comparison">
          {headline ??
            "The two sides differ in model size, weight precision, hardware, and network path at the same time."}
        </Notice>
        {report.simulated && (
          <Notice title="Simulated">
            At least one side was a mock backend that runs no model. These numbers describe the mock,
            not any real model or hardware.
          </Notice>
        )}
        {report.failure && (
          <p role="alert" className="rounded-md border border-down/50 bg-down/5 px-3 py-2 text-sm text-down">
            {report.failure}
          </p>
        )}

        <ModelFacts report={report} />
        <Charts report={report} />
        <ResultsTable rows={report.rows} workloads={workloads} />
        <ResponseViewer report={report} />
        <CloudSideDetails report={report} />

        {otherCaveats.length > 0 && (
          <section>
            <h3 className="text-sm font-medium">How to read these numbers</h3>
            <ul className="mt-2 max-w-[85ch] list-disc space-y-1 pl-5 text-sm text-muted">
              {otherCaveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          </section>
        )}

        <Reproducibility report={report} />

        <div className="flex flex-wrap gap-2 border-t border-line pt-4">
          {EXPORTS.map((item) => (
            <a key={item.format} className={buttonClass} href={comparisonExportUrl(report.id, item.format)} download>
              {item.label}
            </a>
          ))}
        </div>
      </div>
    </Panel>
  );
}

export function ComparisonReportView({ id }: { id: string }) {
  const report = useComparison(id);
  return <QueryView query={report}>{(data) => <Report report={data} />}</QueryView>;
}
