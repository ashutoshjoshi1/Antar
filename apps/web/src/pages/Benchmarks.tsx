import { lazy, Suspense } from "react";

import { PageHeader, Panel, QueryView, Tag } from "../components/ui";
import { useCapabilities, useExperiments, useSettings } from "../lib/api";
import { metricDeltas, titleCase } from "../lib/format";
import type { ExperimentRecord, ModalityInfo } from "../lib/types";

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

export function Benchmarks() {
  const experiments = useExperiments();
  const capabilities = useCapabilities();
  const settings = useSettings();
  const directory = settings.data?.storage.experiments_dir ?? "the experiments directory";

  return (
    <>
      <PageHeader
        title="Benchmarks"
        summary="Recorded experiments, compared against their own baselines. Every number here is read from an experiment record on disk."
      />
      <QueryView query={capabilities}>
        {(catalog) => (
          <div className="space-y-6">
            <QueryView query={experiments}>
              {(records) =>
                records.length === 0 ? (
                  <Panel title="Experiments">
                    <p className="font-medium">No experiments recorded</p>
                    <p className="mt-1 max-w-[70ch] text-sm text-muted">
                      The benchmark runner is not built yet, so nothing has been measured. When a
                      record is written to <code className="font-mono text-ink">{directory}</code>,
                      its baseline and optimized metrics are charted here.
                    </p>
                  </Panel>
                ) : (
                  records.map((experiment) => (
                    <ExperimentCard key={experiment.id} experiment={experiment} catalog={catalog.modalities} />
                  ))
                )
              }
            </QueryView>
            <Panel title="What gets measured for each modality" aside={<Tag>Evaluators not built yet</Tag>}>
              <MetricCatalog catalog={catalog.modalities} />
            </Panel>
          </div>
        )}
      </QueryView>
    </>
  );
}
