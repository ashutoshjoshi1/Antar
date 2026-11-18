import { useEffect, useState } from "react";

import { useCloudCost, useSetCloudCost } from "../../lib/api";
import { elapsedSeconds, isoToLocalInput, localInputToIso, parseAmount } from "../../lib/cloud";
import { formatCount, formatDateTime, formatElapsed, formatMoney } from "../../lib/format";
import type { CloudSession, CostEstimate } from "../../lib/types";
import { buttonClass, fieldClass, Notice, Panel, QueryView, Tag, Value } from "../ui";

const TICK_MS = 1_000;

/** The current time, refreshed every second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(timer);
  }, [active]);
  return now;
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="rounded-md border border-line bg-ground px-3 py-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="tabular mt-1 text-lg">
        <Value>{value}</Value>
      </dd>
      <dd className="mt-0.5 text-2xs text-faint">{note}</dd>
    </div>
  );
}

function Session({ estimate }: { estimate: CostEstimate }) {
  const save = useSetCloudCost();
  const now = useNow(estimate.running);
  const [price, setPrice] = useState(estimate.hourly_price_usd?.toString() ?? "");
  const [credit, setCredit] = useState(estimate.credit_balance_usd?.toString() ?? "");
  const [started, setStarted] = useState(isoToLocalInput(estimate.instance_started_at));

  const session = (changes: Partial<CloudSession>): CloudSession => ({
    hourly_price_usd: estimate.hourly_price_usd,
    credit_balance_usd: estimate.credit_balance_usd,
    instance_started_at: estimate.instance_started_at,
    instance_stopped_at: estimate.instance_stopped_at,
    ...changes,
  });

  const submit = () => {
    const startedAt = localInputToIso(started);
    const sameStart = started === isoToLocalInput(estimate.instance_started_at);
    save.mutate(
      session({
        hourly_price_usd: parseAmount(price),
        credit_balance_usd: parseAmount(credit),
        // The input has minute precision; keep the stored instant unless the user changed it.
        instance_started_at: sameStart ? estimate.instance_started_at : startedAt,
        // A new start time describes a new session, so an old stop time no longer applies.
        instance_stopped_at: sameStart ? estimate.instance_stopped_at : null,
      }),
    );
  };

  return (
    <div className="space-y-5">
      {estimate.warnings.length > 0 && (
        <Notice role="alert" title={estimate.warnings.length === 1 ? "Warning" : "Warnings"}>
          <ul className="list-disc space-y-1 pl-5">
            {estimate.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Notice>
      )}

      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Instance time"
          value={formatElapsed(elapsedSeconds(estimate, now))}
          note={estimate.running ? "Since the start time you entered" : estimate.instance_stopped_at ? "Between your start and stop times" : "No start time entered"}
        />
        <Stat label="Estimated spend" value={formatMoney(estimate.estimated_spend_usd)} note="Instance time × your hourly price" />
        <Stat label="Credit remaining" value={formatMoney(estimate.estimated_remaining_usd)} note="Your balance minus estimated spend" />
        <Stat
          label="Hours remaining"
          value={formatCount(estimate.estimated_hours_remaining, "h")}
          note="At your hourly price"
        />
      </dl>

      <form
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div>
          <label htmlFor="cost-price" className="mb-1.5 block text-sm">
            Hourly price, USD
          </label>
          <input id="cost-price" type="number" min={0} step="any" inputMode="decimal" className={fieldClass} value={price} placeholder="Not entered" onChange={(event) => setPrice(event.target.value)} />
        </div>
        <div>
          <label htmlFor="cost-credit" className="mb-1.5 block text-sm">
            Credit balance, USD
          </label>
          <input id="cost-credit" type="number" min={0} step="any" inputMode="decimal" className={fieldClass} value={credit} placeholder="Not entered" onChange={(event) => setCredit(event.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="cost-started" className="mb-1.5 block text-sm">
            Instance started
          </label>
          <div className="flex gap-2">
            <input id="cost-started" type="datetime-local" className={fieldClass} value={started} onChange={(event) => setStarted(event.target.value)} />
            <button type="button" className={buttonClass} onClick={() => setStarted(isoToLocalInput(new Date().toISOString()))}>
              Now
            </button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-4">
          <button type="submit" disabled={save.isPending} className={buttonClass}>
            {save.isPending ? "Saving…" : "Save"}
          </button>
          {estimate.running && (
            <button
              type="button"
              disabled={save.isPending}
              className={`${buttonClass} border-warn/60 text-warn`}
              onClick={() => save.mutate(session({ instance_stopped_at: new Date().toISOString() }))}
            >
              I stopped it
            </button>
          )}
          {estimate.instance_stopped_at && (
            <button
              type="button"
              disabled={save.isPending}
              className={buttonClass}
              onClick={() => save.mutate(session({ instance_stopped_at: null }))}
            >
              Clear the stop time
            </button>
          )}
        </div>
      </form>

      {save.isError && (
        <p role="alert" className="text-sm text-down">
          {save.error.message}
        </p>
      )}

      {estimate.instance_stopped_at ? (
        <Notice tone="plain" title={`You recorded a stop at ${formatDateTime(estimate.instance_stopped_at)}`}>
          Antar cannot verify this. It did not stop the instance and cannot see whether it still
          exists or is still billing. Confirm it in your provider's console.
        </Notice>
      ) : (
        <p className="max-w-[75ch] text-xs text-faint">
          "I stopped it" only records the time you say billing stopped. Antar never starts, stops,
          or checks an instance.
        </p>
      )}
    </div>
  );
}

export function CostPanel() {
  const cost = useCloudCost();
  return (
    <Panel title="Cost" aside={<Tag>Estimated from numbers you enter</Tag>}>
      <p className="mb-4 max-w-[75ch] text-sm text-muted">
        Antar reads no billing API. Everything here is arithmetic on the price, balance, and start
        time you type in, computed by the Antar API.
      </p>
      {/* Remounting on a new session keeps the fields in step with what the server stored. */}
      <QueryView query={cost}>
        {(estimate) => (
          <Session
            key={[estimate.hourly_price_usd, estimate.credit_balance_usd, estimate.instance_started_at].join("|")}
            estimate={estimate}
          />
        )}
      </QueryView>
    </Panel>
  );
}
