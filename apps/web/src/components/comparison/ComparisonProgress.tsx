import { useEffect, useState } from "react";

import { useCancelComparison } from "../../lib/api";
import { formatElapsed, titleCase } from "../../lib/format";
import type { ComparisonProgress as Progress } from "../../lib/types";
import { LocationBadge } from "../ui";

function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

/** Live progress of the comparison the API is running, or the last one it ran. */
export function ComparisonProgress({ progress }: { progress: Progress }) {
  const cancel = useCancelComparison();
  const running = progress.status === "running";
  const now = useNow(running);
  const fraction = progress.total_requests ? progress.completed_requests / progress.total_requests : 0;
  const elapsed = Math.max(0, (now - Date.parse(progress.started_at)) / 1000);
  const barTone = !running ? "bg-ink/60" : progress.side === "cloud" ? "bg-cloud" : progress.side === "local" ? "bg-local" : "bg-ink/60";

  return (
    <div className="rounded-lg border border-line bg-surface p-5" role="status">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm font-medium break-words">
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
        aria-label="Comparison progress"
        aria-valuemin={0}
        aria-valuemax={progress.total_requests}
        aria-valuenow={progress.completed_requests}
        className="mt-3 h-2 overflow-hidden rounded-full bg-raised"
      >
        <div className={`h-full origin-left rounded-full ${barTone}`} style={{ transform: `scaleX(${fraction})` }} />
      </div>
      <div className="tabular mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
        {running &&
          (progress.side ? (
            <span className="flex items-center gap-2">
              Now running <LocationBadge location={progress.side} />
            </span>
          ) : (
            <span>Preparing</span>
          ))}
        <span>
          {progress.completed_requests} of {progress.total_requests} requests
        </span>
        {running && (
          <span>
            {formatElapsed(elapsed)} of a {formatElapsed(progress.budget_seconds)} budget
          </span>
        )}
      </div>
      {progress.current && running && <p className="mt-1 text-sm break-words text-muted">{progress.current}</p>}
      {progress.failure && <p className="mt-2 text-sm text-down">{progress.failure}</p>}
      {progress.status === "cancelled" && (
        <p className="mt-2 text-sm text-muted">Requests that finished before cancelling were saved.</p>
      )}
      {cancel.isError && (
        <p role="alert" className="mt-2 text-sm text-down">
          {cancel.error.message}
        </p>
      )}
    </div>
  );
}
