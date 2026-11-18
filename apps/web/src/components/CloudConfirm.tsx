import { useCloudCost } from "../lib/api";
import { formatMoney } from "../lib/format";
import { buttonClass } from "./ui";

interface CloudConfirmProps {
  /** What is about to run, e.g. "This comparison". */
  subject: string;
  /** Extra facts about the run, e.g. its time budget. */
  detail?: string;
  simulated?: boolean;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * The explicit step before anything keeps a paid cloud instance busy. Nothing is
 * sent until the user confirms here.
 */
export function CloudConfirm({ subject, detail, simulated = false, pending, onConfirm, onCancel }: CloudConfirmProps) {
  const cost = useCloudCost();
  const price = cost.data?.hourly_price_usd ?? null;
  return (
    <div role="alertdialog" aria-labelledby="cloud-confirm-title" aria-describedby="cloud-confirm-body" className="rounded-md border border-warn/60 bg-warn/5 px-4 py-3 text-sm">
      <p id="cloud-confirm-title" className="font-medium text-warn">
        {simulated ? "Confirm this simulated run" : "This uses paid cloud time"}
      </p>
      <div id="cloud-confirm-body" className="mt-1 max-w-[80ch] space-y-1 text-muted">
        {simulated ? (
          <p>
            {subject} uses a mock backend, so no cloud instance is contacted and every result will
            be labelled Simulated. The same confirmation is required as for a real run.
          </p>
        ) : (
          <p>
            {subject} sends requests to your cloud instance and keeps it busy until it finishes.
            The instance bills for all the time it exists, not only while Antar uses it, and Antar
            does not stop it afterwards.
          </p>
        )}
        {!simulated && (
          <p>
            {cost.isPending
              ? "Checking the hourly price you entered…"
              : price !== null
                ? `Hourly price you entered: ${formatMoney(price)} per hour.`
                : "No hourly price is entered on the AMD Cloud page, so Antar cannot estimate what this costs."}
          </p>
        )}
        {detail && <p>{detail}</p>}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" disabled={pending} onClick={onConfirm} className={`${buttonClass} border-warn/70 text-ink`}>
          {pending ? "Starting…" : simulated ? "Confirm and start" : "Confirm and use cloud time"}
        </button>
        <button type="button" disabled={pending} onClick={onCancel} className={buttonClass}>
          Cancel
        </button>
      </div>
    </div>
  );
}
