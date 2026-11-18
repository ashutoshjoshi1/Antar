import { describeExpectation, pairResponses } from "../../lib/comparison";
import type { ResponsePair } from "../../lib/comparison";
import { formatDuration, formatPercent } from "../../lib/format";
import type { ComparisonReport, RunRecord, Side } from "../../lib/types";
import { LocationBadge, Tag } from "../ui";

function Answer({ side, run }: { side: Side; run: RunRecord | undefined }) {
  return (
    <div className={`min-w-0 rounded-md border border-line border-l-2 bg-ground/50 p-3 ${side === "local" ? "border-l-local" : "border-l-cloud"}`}>
      <p className="flex flex-wrap items-center justify-between gap-2">
        <LocationBadge location={side} />
        {run?.metrics && (
          <span className="tabular text-xs text-muted" title="End to end, measured by the Antar API">
            {formatDuration(run.metrics.latency_ms)}
          </span>
        )}
      </p>
      {!run ? (
        <p className="mt-2 text-sm text-faint">No measured response from this side.</p>
      ) : run.ok ? (
        <p className="mt-2 max-h-56 overflow-y-auto text-sm break-words whitespace-pre-wrap">{run.response}</p>
      ) : (
        <p className="mt-2 text-sm break-words text-down">{run.error}</p>
      )}
      {run && (run.score !== null || run.json_valid !== null || run.score_detail) && (
        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
          {run.score !== null && (
            <Tag tone={run.score >= 1 ? "plain" : "warn"}>
              Score {formatPercent(run.score)}
              {run.score_method ? `, ${run.score_method.replaceAll("_", " ")} rule` : ""}
            </Tag>
          )}
          {run.json_valid !== null && (
            <Tag tone={run.json_valid ? "plain" : "warn"}>{run.json_valid ? "Valid JSON" : "Not valid JSON"}</Tag>
          )}
          {run.score_detail && <span className="break-words">{run.score_detail}</span>}
        </div>
      )}
    </div>
  );
}

function Pair({ pair }: { pair: ResponsePair }) {
  const reference = describeExpectation(pair.prompt);
  return (
    <li className="rounded-md border border-line p-3">
      <p className="text-xs text-faint">
        {pair.workload.name} · {pair.prompt.id}
      </p>
      <p className="mt-1 text-sm break-words whitespace-pre-wrap text-muted">
        {pair.prompt.text}
        {pair.prompt.image && <span className="text-faint"> (image: {pair.prompt.image})</span>}
      </p>
      {reference && <p className="mt-1 text-xs break-words text-faint">{reference}</p>}
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <Answer side="local" run={pair.local} />
        <Answer side="cloud" run={pair.cloud} />
      </div>
    </li>
  );
}

/** Each prompt with the local answer next to the cloud answer. */
export function ResponseViewer({ report }: { report: ComparisonReport }) {
  const pairs = pairResponses(report);
  if (pairs.length === 0) return null;
  return (
    <details>
      <summary className="cursor-pointer text-sm select-none">Responses side by side ({pairs.length} prompts)</summary>
      <p className="mt-2 max-w-[75ch] text-xs text-muted">
        The first measured answer to each prompt from either side. Scores come from the Antar scorer
        applying a fixed rule to a reference answer; prompts without a reference are not scored.
      </p>
      <ol className="mt-3 space-y-4">
        {pairs.map((pair) => (
          <Pair key={pair.key} pair={pair} />
        ))}
      </ol>
    </details>
  );
}
