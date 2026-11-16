import { useEffect, useState } from "react";

import { formatCount, formatDuration } from "../../lib/format";
import type { Turn } from "../../lib/useChat";

function Row({ label, value, source }: { label: string; value: string; source?: string }) {
  const unavailable = value === "Unavailable";
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line/60 py-2 last:border-0">
      <dt className="text-sm text-muted">
        {label}
        {source && <span className="block text-2xs text-faint">{source}</span>}
      </dt>
      <dd className={`tabular text-right text-sm ${unavailable ? "text-faint" : ""}`}>{value}</dd>
    </div>
  );
}

/** Ticks while a response is being generated. */
export function Elapsed({ startedAt }: { startedAt: number }) {
  const [now, setNow] = useState(() => performance.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(performance.now()), 100);
    return () => window.clearInterval(timer);
  }, []);
  return <span className="tabular">{((now - startedAt) / 1000).toFixed(1)} s</span>;
}

/**
 * Measurements for one reply. Each row says who measured it, because the
 * backend's generation time and the time spent waiting in the browser differ.
 */
export function MetricsPanel({ turn }: { turn: Turn | undefined }) {
  if (!turn) {
    return <p className="text-sm text-muted">Measurements appear here after a response.</p>;
  }
  const metrics = turn.metrics;
  if (!metrics) {
    return (
      <dl>
        <Row label="Waited in the browser" value={formatDuration(turn.elapsedMs)} />
        <p className="pt-3 text-xs text-faint">
          Generation was stopped, so the model server reported no token counts or timings.
        </p>
      </dl>
    );
  }
  const cached = metrics.cached_prompt_tokens;
  return (
    <dl>
      <Row label="Generation speed" value={formatCount(metrics.tokens_per_second, "tokens/s")} source="Reported by Lemonade" />
      <Row label="Output tokens" value={formatCount(metrics.completion_tokens)} source="Reported by Lemonade" />
      <Row
        label="Input tokens"
        value={formatCount(metrics.prompt_tokens) + (cached ? ` (${cached} cached)` : "")}
        source="Reported by Lemonade"
      />
      <Row label="Prompt processing" value={formatDuration(metrics.prompt_processing_ms)} source="Reported by Lemonade" />
      <Row label="Generation time" value={formatDuration(metrics.generation_ms)} source="Reported by Lemonade" />
      <Row label="First chunk" value={formatDuration(metrics.first_chunk_ms)} source="Measured by the Antar API" />
      <Row label="Whole request" value={formatDuration(metrics.latency_ms)} source="Measured by the Antar API" />
      <Row label="Waited in the browser" value={formatDuration(turn.elapsedMs)} source="Includes the network" />
    </dl>
  );
}
