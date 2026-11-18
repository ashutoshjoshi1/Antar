import { usePreflight } from "../../lib/api";
import { formatDateTime, titleCase } from "../../lib/format";
import type { CheckStatus, PreflightReport } from "../../lib/types";
import { buttonClass, Fact, Notice, Panel } from "../ui";

const CHECK_STYLES: Record<CheckStatus, { label: string; className: string }> = {
  pass: { label: "Pass", className: "border-ok/50 text-ok" },
  warn: { label: "Warn", className: "border-warn/50 text-warn" },
  fail: { label: "Fail", className: "border-down/50 text-down" },
  skip: { label: "Skipped", className: "border-line text-faint" },
};

function Report({ report }: { report: PreflightReport }) {
  const failed = report.checks.filter((check) => check.status === "fail").length;
  const warned = report.checks.filter((check) => check.status === "warn").length;
  const facts = Object.entries(report.facts);
  return (
    <div className="mt-4 space-y-4">
      <p className="text-sm">
        {failed > 0 ? (
          <span className="text-down">{failed} failed</span>
        ) : (
          <span className="text-ok">No check failed</span>
        )}
        {warned > 0 && <span className="text-warn">, {warned} with warnings</span>}
        <span className="text-muted"> of {report.checks.length} checks. Run {formatDateTime(report.checked_at)}.</span>
      </p>
      <ul className="space-y-2">
        {report.checks.map((check) => {
          const style = CHECK_STYLES[check.status];
          return (
            <li key={check.id} className="flex gap-3 rounded-md border border-line px-3 py-2.5">
              <span className={`h-fit w-16 shrink-0 rounded border px-1.5 py-0.5 text-center text-2xs ${style.className}`}>
                {style.label}
              </span>
              <div className="min-w-0 text-sm">
                <p className="font-mono text-xs text-muted">{check.id}</p>
                <p className="mt-0.5 break-words">{check.detail}</p>
                {check.remediation && (
                  <p className="mt-1 break-words text-muted">
                    <span className="text-ink">To fix:</span> {check.remediation}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      {facts.length > 0 && (
        <details>
          <summary className="cursor-pointer text-sm select-none">What the host reported ({facts.length})</summary>
          <dl className="mt-2 grid gap-x-10 sm:grid-cols-2">
            {facts.map(([key, value]) => (
              <Fact key={key} term={titleCase(key)}>
                <span className="font-mono text-xs">{value}</span>
              </Fact>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}

/** The preflight is slow and opens an SSH session, so it runs only when asked. */
export function PreflightPanel({ sshConfigured }: { sshConfigured: boolean }) {
  const preflight = usePreflight();
  return (
    <Panel title="Environment preflight">
      <p className="max-w-[75ch] text-sm text-muted">
        Runs a read-only script on the AMD host over SSH to check the driver, ROCm, container
        runtime, and disk. It changes nothing there, can take a while, and never runs on its own.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!sshConfigured || preflight.isPending}
          onClick={() => preflight.mutate()}
          className={buttonClass}
        >
          {preflight.isPending ? "Running preflight…" : "Run preflight"}
        </button>
        {!sshConfigured && (
          <p className="text-sm text-muted">Needs an SSH host: add an amd_cloud profile to the configuration.</p>
        )}
      </div>
      {preflight.isError && (
        <div className="mt-4">
          <Notice tone="down" role="alert" title="The preflight could not run">
            {preflight.error.message}
          </Notice>
        </div>
      )}
      {preflight.data && <Report report={preflight.data} />}
    </Panel>
  );
}
