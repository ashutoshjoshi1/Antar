import { useState } from "react";

import { useLemonadeProvider, useLemonadeProviderAction } from "../../lib/api";
import type { LemonadeProviderStatus } from "../../lib/types";
import { buttonClass, Fact, Notice, Panel, QueryView, Tag } from "../ui";

type ProviderState = "unreachable" | "unsupported" | "not_registered" | "registered";

export function providerState(status: LemonadeProviderStatus): ProviderState {
  if (!status.lemonade_reachable) return "unreachable";
  if (status.supported !== true) return "unsupported";
  return status.provider ? "registered" : "not_registered";
}

const STATES: Record<ProviderState, { label: string; className: string }> = {
  unreachable: { label: "Lemonade is not reachable", className: "text-down" },
  unsupported: { label: "Not supported by this Lemonade", className: "text-warn" },
  not_registered: { label: "Not registered", className: "text-muted" },
  registered: { label: "Registered", className: "text-ok" },
};

interface ProviderProps {
  status: LemonadeProviderStatus;
  endpointConfigured: boolean;
}

function Provider({ status, endpointConfigured }: ProviderProps) {
  const action = useLemonadeProviderAction();
  const [confirming, setConfirming] = useState(false);
  const state = providerState(status);
  const provider = status.provider;
  const canAct = state === "registered" || state === "not_registered";

  return (
    <div className="space-y-4">
      <div role="status" className="rounded-md border border-line bg-ground px-3 py-2.5">
        <p className={`text-sm font-medium ${STATES[state].className}`}>{STATES[state].label}</p>
        {status.detail && <p className="mt-1 text-sm break-words text-muted">{status.detail}</p>}
        <p className="mt-1 text-xs text-faint">
          Provider name in Lemonade: <span className="font-mono">{status.name}</span>
        </p>
      </div>

      {provider && (
        <>
          <dl>
            <Fact term="Endpoint Lemonade holds">
              <span className="font-mono text-xs break-all">{provider.base_url ?? "Not reported"}</span>
            </Fact>
            <Fact term="Models discovered">
              {provider.models_discovered === null ? <span className="text-faint">Unavailable</span> : provider.models_discovered}
            </Fact>
            <Fact term="Key held by Lemonade">
              {provider.runtime_key_set === null ? "Not reported" : provider.runtime_key_set ? "Yes, in memory" : "No"}
            </Fact>
            <Fact term="Plain HTTP allowed">
              {provider.allow_insecure_http === null ? "Not reported" : provider.allow_insecure_http ? "Yes" : "No"}
            </Fact>
          </dl>
          {provider.warnings.length > 0 && (
            <Notice title="Warnings from Lemonade">
              <ul className="list-disc space-y-1 pl-5">
                {provider.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </Notice>
          )}
        </>
      )}

      {confirming && (
        <div role="alertdialog" aria-labelledby="provider-confirm-title" className="rounded-md border border-warn/60 bg-warn/5 px-4 py-3 text-sm">
          <p id="provider-confirm-title" className="font-medium text-warn">
            Register the cloud endpoint with Lemonade?
          </p>
          <p className="mt-1 max-w-[75ch] text-muted">
            This changes Lemonade's configuration, not just Antar's, and hands Lemonade the cloud
            endpoint's API key, which Lemonade then holds. Other apps that use this Lemonade server
            will be able to send requests to your cloud endpoint through it.
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={action.isPending}
              className={`${buttonClass} border-warn/70`}
              onClick={() => action.mutate("register", { onSettled: () => setConfirming(false) })}
            >
              {action.isPending ? "Registering…" : "Confirm and register"}
            </button>
            <button type="button" disabled={action.isPending} className={buttonClass} onClick={() => setConfirming(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!canAct || !endpointConfigured || confirming || action.isPending}
          className={buttonClass}
          onClick={() => setConfirming(true)}
        >
          {state === "registered" ? "Register again…" : "Register…"}
        </button>
        {state === "registered" && (
          <button type="button" disabled={action.isPending} className={buttonClass} onClick={() => action.mutate("remove")}>
            {action.isPending && action.variables === "remove" ? "Removing…" : "Remove"}
          </button>
        )}
        {!endpointConfigured && (
          <p className="text-sm text-muted">
            Registering is unavailable: no cloud endpoint is configured, so there is nothing to
            register.
          </p>
        )}
      </div>
      {action.isError && (
        <p role="alert" className="text-sm text-down">
          {action.error.message}
        </p>
      )}
    </div>
  );
}

/** Lemonade can route requests to a cloud provider itself. Antar only registers its endpoint there. */
export function LemonadeProviderPanel({ endpointConfigured }: { endpointConfigured: boolean }) {
  const provider = useLemonadeProvider();
  return (
    <Panel title="Lemonade cloud provider" aside={<Tag tone="warn">Experimental in Lemonade</Tag>} className="lg:col-span-2">
      <p className="mb-4 max-w-[75ch] text-sm text-muted">
        Lemonade can forward requests to a cloud provider on its own. Registering Antar's cloud
        endpoint there makes its models appear in Lemonade alongside the local ones. Antar does not
        need this to use the cloud endpoint.
      </p>
      <QueryView query={provider}>
        {(status) => <Provider status={status} endpointConfigured={endpointConfigured} />}
      </QueryView>
    </Panel>
  );
}
