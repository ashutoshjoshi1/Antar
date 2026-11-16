import { useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useEffect } from "react";
import { useSearchParams } from "react-router";

import { BenchmarkForm } from "../components/benchmarks/BenchmarkForm";
import { ReportView } from "../components/benchmarks/ReportView";

import { PageHeader, Panel, QueryView, Tag } from "../components/ui";
import {
  useActiveBenchmark,
  useBenchmarkHistory,
  useCancelBenchmark,
  useCapabilities,
  useExperiments,
  useModels,
  useSettings,
  useWorkloads,
} from "../lib/api";
import { formatCount, formatDuration, metricDeltas, titleCase } from "../lib/format";
import type { BenchmarkProgress, ExperimentRecord, ModalityInfo, ReportSummary } from "../lib/types";

// Recharts is only needed once an experiment has comparable results.
const DeltaChart = lazy(() => import("../components/DeltaChart"));

function ExperimentCard({ experiment, catalog }: { experiment: ExperimentRecord; catalog: ModalityInfo[] }) {
  const modality = experiment.baseline?.modality ?? experiment.optimized?.modality;
  const specs = catalog.find((info) => info.modality === modality)?.metrics ?? [];
  const deltas = metricDeltas(experiment, specs);
  const simulated = Boolean(experiment.baseline?.simulated || experiment.optimized?.simulated);

  return (
    <Panel
      title={experiment.name}
      aside={
        <span className="flex items-center gap-2">
          {simulated && <Tag tone="warn">Simulated, not a real result</Tag>}
          <span className="font-mono text-xs text-faint">{experiment.id}</span>
        </span>
      }
    >
      <p className="font-mono text-xs text-muted">
        {experiment.model.id}
        {experiment.model.revision && `@${experiment.model.revision}`} on {experiment.backend}
      </p>
      {deltas.length > 0 ? (
        <Suspense fallback={<p className="mt-4 text-sm text-muted">Loading chart…</p>}>
          <div className="mt-4" aria-hidden>
            <DeltaChart deltas={deltas} />
          </div>
          <ul className="sr-only">
            {deltas.map((delta) => (
              <li key={delta.key}>
                {delta.name}: {(delta.change * 100).toFixed(1)}% change from baseline,{" "}
                {delta.change === 0 ? "unchanged" : delta.improved ? "better" : "worse"}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-faint">
            Green means the metric moved in its better direction. {experiment.optimized?.methodology}
          </p>
        </Suspense>
      ) : (
        <p className="mt-4 text-sm text-muted">
          This experiment has no metric measured in both the baseline and the optimized run, so
          there is nothing to compare yet.
        </p>
      )}
    </Panel>
  );
}

function MetricCatalog({ catalog }: { catalog: ModalityInfo[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] border-separate border-spacing-0 text-sm">
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="pb-3 font-normal">Modality</th>
            <th scope="col" className="pb-3 font-normal">Quality</th>
            <th scope="col" className="pb-3 font-normal">Performance</th>
          </tr>
        </thead>
        <tbody>
          {catalog.map((info) => (
            <tr key={info.modality} className="align-top">
              <th scope="row" className="border-t border-line py-3 pr-4 text-left font-medium">
                {titleCase(info.modality)}
              </th>
              {(["quality", "performance"] as const).map((kind) => (
                <td key={kind} className="border-t border-line py-3 pr-4 text-muted">
                  <ul className="space-y-1">
                    {info.metrics
                      .filter((metric) => metric.kind === kind)
                      .map((metric) => (
                        <li key={metric.key}>
                          {metric.name}{" "}
                          <span className="text-faint">
                            ({metric.higher_is_better ? "higher" : "lower"} is better)
                          </span>
                        </li>
                      ))}
                  </ul>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Progress({ progress }: { progress: BenchmarkProgress }) {
  const cancel = useCancelBenchmark();
  const fraction = progress.total_requests ? progress.completed_requests / progress.total_requests : 0;
  const running = progress.status === "running";
  return (
    <div className="rounded-lg border border-line bg-surface p-5" role="status">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium">
          {running ? "Running" : titleCase(progress.status)}: {progress.name}
        </p>
        {running && (
          <button
            type="button"
            disabled={cancel.isPending}
            onClick={() => cancel.mutate()}
            className="rounded-md border border-down/60 px-3 py-1.5 text-sm text-down hover:bg-down/10 disabled:opacity-50"
          >
            {cancel.isPending ? "Cancelling…" : "Cancel"}
          </button>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="Benchmark progress"
        aria-valuemin={0}
        aria-valuemax={progress.total_requests}
        aria-valuenow={progress.completed_requests}
        className="mt-3 h-2 overflow-hidden rounded-full bg-raised"
      >
        <div className={`h-full origin-left rounded-full ${running ? "bg-local" : "bg-ink/60"}`} style={{ transform: `scaleX(${fraction})` }} />
      </div>
      <p className="tabular mt-2 text-sm text-muted">
        {progress.completed_requests} of {progress.total_requests} requests
        {progress.current && running ? `. ${progress.current}` : ""}
      </p>
      {progress.failure && <p className="mt-2 text-sm text-down">{progress.failure}</p>}
      {progress.status === "cancelled" && (
        <p className="mt-2 text-sm text-muted">Requests that finished before cancelling were saved.</p>
      )}
    </div>
  );
}

function History({ reports, selected, onSelect }: { reports: ReportSummary[]; selected: string | null; onSelect: (id: string) => void }) {
  if (reports.length === 0) {
    return (
      <p className="text-sm text-muted">
        No benchmark has been run yet. Results appear here once one finishes; nothing is shown that
        was not measured.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] border-separate border-spacing-0 text-sm">
        <thead className="text-left text-muted">
          <tr>
            <th scope="col" className="pb-2 font-normal">Model</th>
            <th scope="col" className="pb-2 font-normal">Started</th>
            <th scope="col" className="pb-2 text-right font-normal">Requests</th>
            <th scope="col" className="pb-2 text-right font-normal">Median latency</th>
            <th scope="col" className="pb-2 text-right font-normal">Median tokens/s</th>
            <th scope="col" className="pb-2 font-normal"><span className="sr-only">Open</span></th>
          </tr>
        </thead>
        <tbody>
          {reports.map((report) => (
            <tr key={report.id} className={report.id === selected ? "bg-raised/50" : "hover:bg-raised/30"}>
              <td className="border-t border-line py-2 pr-4">
                <span className="font-mono text-[0.8125rem]">{report.model}</span>
                <span className="ml-2 inline-flex gap-1">
                  {report.quantization && <Tag>{report.quantization}</Tag>}
                  {report.simulated && <Tag tone="warn">Simulated</Tag>}
                  {report.status !== "completed" && <Tag tone="warn">{report.status}</Tag>}
                </span>
              </td>
              <td className="border-t border-line py-2 pr-4 text-muted">{new Date(report.started_at).toLocaleString()}</td>
              <td className="tabular border-t border-line py-2 text-right">{report.overall?.completed ?? 0}</td>
              <td className="tabular border-t border-line py-2 text-right">{formatDuration(report.overall?.latency_ms_median)}</td>
              <td className="tabular border-t border-line py-2 text-right">{formatCount(report.overall?.tokens_per_second_median)}</td>
              <td className="border-t border-line py-2 pl-4 text-right">
                <button type="button" onClick={() => onSelect(report.id)} aria-pressed={report.id === selected} className="rounded border border-line px-2 py-1 text-xs hover:border-muted">
                  {report.id === selected ? "Showing" : "View"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Lab() {
  const models = useModels();
  const workloads = useWorkloads();
  const history = useBenchmarkHistory();
  const active = useActiveBenchmark();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selected = params.get("report");
  const status = active.data?.status;

  // When a run finishes, its report is now in the history.
  useEffect(() => {
    if (status && status !== "running") void client.invalidateQueries({ queryKey: ["benchmarks"] });
  }, [status, client]);

  const shown = selected ?? history.data?.[0]?.id ?? null;
  return (
    <div className="space-y-6">
      <Panel title="Run a benchmark">
        <QueryView query={models}>
          {(inventory) => (
            <QueryView query={workloads}>
              {(items) => {
                const usable = inventory.models.filter(
                  (model) => !model.simulated && model.downloaded === true && model.tasks.includes("chat"),
                );
                return usable.length === 0 ? (
                  <p className="text-sm text-muted">
                    No downloaded chat model is available. Download one on the Models page, and check
                    that Lemonade is running.
                  </p>
                ) : (
                  <BenchmarkForm models={usable} workloads={items} running={status === "running"} />
                );
              }}
            </QueryView>
          )}
        </QueryView>
      </Panel>

      {active.data && <Progress progress={active.data} />}

      <Panel title="Completed runs">
        <QueryView query={history}>
          {(reports) => (
            <History reports={reports} selected={shown} onSelect={(id) => setParams({ report: id }, { replace: true })} />
          )}
        </QueryView>
      </Panel>

      {shown && history.data && <ReportView key={shown} id={shown} history={history.data} />}
    </div>
  );
}

export function Benchmarks() {
  const experiments = useExperiments();
  const capabilities = useCapabilities();
  const settings = useSettings();
  const directory = settings.data?.storage.experiments_dir ?? "the experiments directory";

  return (
    <>
      <PageHeader
        title="Benchmarks"
        summary="Measure a local model on fixed prompt sets. Every number here comes from a request that actually ran, and each run is saved as a report you can export."
      />
      <Lab />
      <h2 className="mt-12 mb-4 text-lg font-semibold tracking-tight">Optimization experiments</h2>
      <QueryView query={capabilities}>
        {(catalog) => (
          <div className="space-y-6">
            <QueryView query={experiments}>
              {(records) =>
                records.length === 0 ? (
                  <Panel title="Experiments">
                    <p className="font-medium">No experiments recorded</p>
                    <p className="mt-1 max-w-[70ch] text-sm text-muted">
                      An experiment compares a model before and after optimization. No optimization
                      can run yet, so there is nothing to compare. Records written to{" "}
                      <code className="font-mono text-ink">{directory}</code> are charted here.
                    </p>
                  </Panel>
                ) : (
                  records.map((experiment) => (
                    <ExperimentCard key={experiment.id} experiment={experiment} catalog={catalog.modalities} />
                  ))
                )
              }
            </QueryView>
            <Panel title="What gets measured for each modality" aside={<Tag>Quality evaluators not built yet</Tag>}>
              <MetricCatalog catalog={catalog.modalities} />
            </Panel>
          </div>
        )}
      </QueryView>
    </>
  );
}
