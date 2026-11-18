import { connectionState } from "../../lib/cloud";
import type { ConnectionState } from "../../lib/cloud";
import { formatDateTime, formatDuration } from "../../lib/format";
import type { CloudStatus } from "../../lib/types";
import { buttonClass, Fact, LocationBadge, Panel, Value } from "../ui";

const STATES: Record<ConnectionState, { label: string; dot: string; text: string; help: string }> = {
  not_configured: {
    label: "Not configured",
    dot: "bg-faint",
    text: "text-muted",
    help: "No cloud endpoint is set, so Antar has not tried to connect to anything.",
  },
  unreachable: {
    label: "Unreachable",
    dot: "bg-down",
    text: "text-down",
    help: "Antar checks again every 15 seconds while this page is open.",
  },
  loading_model: {
    label: "Loading model",
    dot: "bg-warn",
    text: "text-warn",
    help: "The server answered but is not ready. Antar checks again every 15 seconds.",
  },
  connected: {
    label: "Connected",
    dot: "bg-ok",
    text: "text-ok",
    help: "Reported by the endpoint's own health check just now.",
  },
};

function pathLabel(loopback: boolean | null): string {
  if (loopback === null) return "Unavailable";
  return loopback
    ? "Loopback: an SSH tunnel or a server on this machine"
    : "Not loopback: a host listed as trusted in the configuration";
}

interface ConnectionPanelProps {
  status: CloudStatus;
  checking: boolean;
  onCheck: () => void;
}

/** Only what the API reported. A state or a model the API did not report is never shown. */
export function ConnectionPanel({ status, checking, onCheck }: ConnectionPanelProps) {
  const state = connectionState(status);
  const style = STATES[state];
  return (
    <Panel
      title="Connection"
      aside={
        <button type="button" onClick={onCheck} className={`${buttonClass} px-2.5 py-1 text-xs`}>
          {checking ? "Checking…" : "Check again"}
        </button>
      }
    >
      <div role="status" className="mb-4 rounded-md border border-line bg-ground px-3 py-2.5">
        <p className={`flex items-center gap-2 text-sm font-medium ${style.text}`}>
          <span aria-hidden className={`size-2 rounded-full ${style.dot}`} />
          {style.label}
        </p>
        <p className="mt-1 text-sm break-words text-muted">{status.status.detail}</p>
        <p className="mt-1 text-xs text-faint">{style.help}</p>
      </div>

      {status.endpoint_configured && (
        <dl>
          <Fact term="Endpoint">
            <span className="font-mono text-xs break-all">{status.base_url ?? "Unavailable"}</span>
          </Fact>
          <Fact term="Network path">{pathLabel(status.loopback)}</Fact>
          <Fact term="API key">{status.api_key_configured ? "Configured" : "Not set"}</Fact>
          <Fact term="Round trip">
            <Value>{formatDuration(status.round_trip_ms)}</Value>
            <span className="block text-2xs text-faint">One GET /health, measured by the Antar API</span>
          </Fact>
          <Fact term="vLLM version">
            <Value>{status.status.version ?? "Unavailable"}</Value>
          </Fact>
          <Fact term="vLLM image">
            {status.vllm_image ? (
              <>
                <span className="font-mono text-xs break-all">{status.vllm_image}</span>
                <span className="block text-2xs text-faint">As declared in the configuration, not probed</span>
              </>
            ) : (
              "Not declared"
            )}
          </Fact>
          <Fact term="Last checked">{formatDateTime(status.status.checked_at)}</Fact>
        </dl>
      )}

      {state === "connected" && (
        <div className="mt-5">
          <h3 className="text-sm font-medium">Served models</h3>
          {status.models.length === 0 ? (
            <p className="mt-1 text-sm text-muted">The endpoint reported no models.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {status.models.map((model) => (
                <li key={model.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 rounded-md border border-line px-3 py-2">
                  <span className="font-mono text-[0.8125rem] break-all">{model.id}</span>
                  <span className="flex items-center gap-3 text-xs text-muted">
                    {model.state === "loaded" ? "Loaded" : "Configured, not served"}
                    <LocationBadge location={model.location} detail={model.provider} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Panel>
  );
}
