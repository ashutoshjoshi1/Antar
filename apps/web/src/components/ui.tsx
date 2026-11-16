import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { Availability } from "../lib/types";

interface PageHeaderProps {
  title: string;
  summary: string;
  actions?: ReactNode;
}

export function PageHeader({ title, summary, actions }: PageHeaderProps) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 max-w-[62ch] text-muted">{summary}</p>
      </div>
      {actions}
    </header>
  );
}

interface PanelProps {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Panel({ title, aside, children, className = "" }: PanelProps) {
  return (
    <section className={`rounded-lg border border-line bg-surface ${className}`}>
      {title && (
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          <h2 className="text-sm font-medium">{title}</h2>
          {aside}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

const AVAILABILITY: Record<Availability, { label: string; dot: string; text: string }> = {
  available: { label: "Available", dot: "bg-ok", text: "text-ok" },
  unavailable: { label: "Unavailable", dot: "bg-down", text: "text-down" },
  not_configured: { label: "Not configured", dot: "bg-faint", text: "text-muted" },
  not_implemented: { label: "Not implemented", dot: "bg-warn", text: "text-warn" },
};

export function StatusPill({ availability }: { availability: Availability }) {
  const style = AVAILABILITY[availability];
  return (
    <span className={`inline-flex items-center gap-2 whitespace-nowrap text-sm ${style.text}`}>
      <span aria-hidden className={`size-2 rounded-full ${style.dot}`} />
      {style.label}
    </span>
  );
}

export function Tag({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "warn" }) {
  const tones = {
    plain: "border-line text-muted",
    warn: "border-warn/50 text-warn",
  };
  return (
    <span className={`rounded border px-1.5 py-0.5 text-2xs whitespace-nowrap ${tones[tone]}`}>
      {children}
    </span>
  );
}

/** Marks a feature the platform does not have yet. Never styled as a success state. */
export function NotBuiltYet({ children }: { children: ReactNode }) {
  return (
    <div
      role="note"
      className="mb-6 rounded-lg border border-dashed border-warn/60 bg-warn/5 px-5 py-4 text-sm"
    >
      <p className="font-medium text-warn">Not built yet</p>
      <p className="mt-1 max-w-[75ch] text-muted">{children}</p>
    </div>
  );
}

interface MeterProps {
  label: string;
  fraction: number;
  detail: string;
}

export function Meter({ label, fraction, detail }: MeterProps) {
  const percent = Math.round(fraction * 100);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>{label}</span>
        <span className="tabular text-muted">{detail}</span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="mt-2 h-2 overflow-hidden rounded-full bg-raised"
      >
        <div
          className={`h-full origin-left rounded-full ${percent >= 90 ? "bg-warn" : "bg-ink/70"}`}
          style={{ transform: `scaleX(${fraction})` }}
        />
      </div>
    </div>
  );
}

export function Fact({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-6 border-b border-line/60 py-2 last:border-0">
      <dt className="shrink-0 text-sm text-muted">{term}</dt>
      <dd className="min-w-0 text-right text-sm break-words">{children}</dd>
    </div>
  );
}

interface QueryViewProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}

/** Renders loading and error states so pages only describe the success case. */
export function QueryView<T>({ query, children }: QueryViewProps<T>) {
  if (query.isPending) {
    return (
      <p role="status" className="text-sm text-muted">
        Loading…
      </p>
    );
  }
  if (query.isError) {
    return (
      <div role="alert" className="rounded-lg border border-down/50 bg-down/5 px-5 py-4 text-sm">
        <p className="text-down">{query.error.message}</p>
        <button
          type="button"
          onClick={() => void query.refetch()}
          className="mt-3 rounded border border-line px-3 py-1.5 text-ink hover:border-ink/60 active:bg-raised"
        >
          Try again
        </button>
      </div>
    );
  }
  return <>{children(query.data)}</>;
}
