import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { Link, useSearchParams } from "react-router";

import { ComparisonForm } from "../components/comparison/ComparisonForm";
import { ComparisonProgress } from "../components/comparison/ComparisonProgress";
import { ComparisonReportView } from "../components/comparison/ComparisonReportView";
import { Notice, PageHeader, Panel, QueryView } from "../components/ui";
import { useActiveComparison, useCloudCost, useComparisonHistory, useModels, useWorkloads } from "../lib/api";

const FALLBACK_BUDGET_MINUTES = 30;

export function ComparisonLab() {
  const models = useModels();
  const workloads = useWorkloads();
  const cost = useCloudCost();
  const active = useActiveComparison();
  const history = useComparisonHistory();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const status = active.data?.status;

  // When a run finishes, its report is now in the history.
  useEffect(() => {
    if (status && status !== "running") void client.invalidateQueries({ queryKey: ["comparisons"] });
  }, [status, client]);

  // A linked report wins; otherwise show the one that just finished, then the newest saved.
  const finished = active.data && active.data.status !== "running" ? active.data.id : null;
  const saved = history.data ?? [];
  const shown =
    params.get("report") ??
    (finished && saved.some((item) => item.id === finished) ? finished : (saved[0]?.id ?? null));

  return (
    <>
      <PageHeader
        title="Comparison Lab"
        summary="Run the same workloads on one local model and one cloud model, with identical settings, and read the two results side by side. It shows what a user gets from each place, not which hardware is faster."
      />
      <div className="space-y-6">
        <Panel title="Set up a comparison">
          <QueryView query={models}>
            {(inventory) => (
              <QueryView query={workloads}>
                {(items) => (
                  <ComparisonForm
                    // The budget field starts from the configured limit once it is known.
                    key={cost.data?.max_experiment_minutes ?? "default"}
                    models={inventory.models}
                    workloads={items}
                    defaultBudgetMinutes={cost.data?.max_experiment_minutes ?? FALLBACK_BUDGET_MINUTES}
                    running={status === "running"}
                  />
                )}
              </QueryView>
            )}
          </QueryView>
        </Panel>

        {active.isError && (
          <Notice tone="down" role="alert" title="Progress is not available">
            {active.error.message}
          </Notice>
        )}
        {active.data && <ComparisonProgress progress={active.data} />}

        {shown ? (
          <ComparisonReportView key={shown} id={shown} />
        ) : (
          <Panel title="Report">
            <QueryView query={history}>
              {() => (
                <p className="text-sm text-muted">
                  No comparison has been run yet. A report appears here once one finishes; nothing is
                  shown that was not measured.
                </p>
              )}
            </QueryView>
          </Panel>
        )}
        <p className="text-sm text-muted">
          Every saved comparison is listed in{" "}
          <Link to="/history" className="text-ink underline">
            Experiment History
          </Link>
          .
        </p>
      </div>
    </>
  );
}
