import { useState } from "react";
import { useSearchParams } from "react-router";

import { ModelFilterBar } from "../components/models/ModelFilterBar";
import { LocationBadge, PageHeader, Panel, QueryView, StatusPill, Tag } from "../components/ui";
import { useDownloads, useModelAction, useModels } from "../lib/api";
import { formatBytes, formatParameters, titleCase } from "../lib/format";
import { filterModels, isRunning, modelKey, parseFilters } from "../lib/models";
import type { DownloadJob, ModelInventory, ModelSpec } from "../lib/types";

const actionClass =
  "rounded border border-line px-2 py-1 text-xs whitespace-nowrap transition-colors hover:border-muted disabled:cursor-not-allowed disabled:opacity-50";

interface ModelRowProps {
  model: ModelSpec;
  download: DownloadJob | undefined;
}

function ModelActions({ model, download }: ModelRowProps) {
  const action = useModelAction();
  const [confirming, setConfirming] = useState(false);
  const busy = action.isPending;

  if (model.simulated) return null;
  if (model.location === "cloud") {
    // The cloud server serves what it was started with; there is nothing to load or fetch from here.
    return (
      <span className="block max-w-44 text-2xs text-faint">
        {model.backend === "amd_cloud"
          ? "Served by vLLM as it was started. No load, unload, or download from here."
          : "Routed to a cloud provider. Nothing to load or download."}
      </span>
    );
  }
  if (download && !download.complete) {
    return (
      <span className="tabular text-xs text-muted">
        Downloading{download.percent !== null ? ` ${Math.round(download.percent)}%` : "…"}
      </span>
    );
  }
  if (model.downloaded === false) {
    return confirming ? (
      <span className="flex items-center gap-1.5">
        <button
          type="button"
          disabled={busy}
          className={`${actionClass} border-local/60 text-ink`}
          onClick={() => {
            action.mutate({ action: "download", model });
            setConfirming(false);
          }}
        >
          Download {formatBytes(model.size_bytes) === "—" ? "(size unknown)" : formatBytes(model.size_bytes)}
        </button>
        <button type="button" className={actionClass} onClick={() => setConfirming(false)}>
          Cancel
        </button>
      </span>
    ) : (
      <button type="button" className={actionClass} onClick={() => setConfirming(true)}>
        Download…
      </button>
    );
  }
  if (model.downloaded !== true) return null;
  return (
    <span className="flex flex-col items-start gap-1">
      <button
        type="button"
        disabled={busy}
        className={actionClass}
        onClick={() => action.mutate({ action: model.loaded ? "unload" : "load", model })}
      >
        {busy ? "Working…" : model.loaded ? "Unload" : "Load"}
      </button>
      {action.isError && (
        <span role="alert" className="max-w-56 text-2xs text-down">
          {action.error.message}
        </span>
      )}
    </span>
  );
}

function ModelState({ model }: { model: ModelSpec }) {
  if (model.simulated) return <Tag tone="warn">Simulated</Tag>;
  if (isRunning(model)) {
    return <span className={model.location === "cloud" ? "text-cloud" : "text-local"}>Loaded</span>;
  }
  if (model.state === "configured") {
    return (
      <span className="text-faint" title="Declared in Antar's configuration; the server is not serving it.">
        Configured, not served
      </span>
    );
  }
  if (model.downloaded) return <span className="text-ok">Downloaded</span>;
  if (model.downloaded === false) return <span className="text-faint">In catalog</span>;
  return <span className="text-faint">Unknown</span>;
}

function ModelRow({ model, download }: ModelRowProps) {
  const capabilities = model.labels.filter((label) =>
    ["reasoning", "tool-calling", "vision", "coding"].includes(label),
  );
  const parameters = formatParameters(model.parameter_count);
  const facts = [
    model.family && `Family ${model.family}`,
    model.license && `License ${model.license}`,
    model.revision && `Revision ${model.revision.slice(0, 12)}`,
  ].filter(Boolean);
  return (
    <tr className="align-top hover:bg-raised/40">
      <td className="border-t border-line py-2.5 pr-4 pl-5">
        <span className="font-mono text-[0.8125rem] break-all">{model.id}</span>
        {model.checkpoint && (
          <span className="mt-0.5 block font-mono text-2xs break-all text-faint">{model.checkpoint}</span>
        )}
        {facts.length > 0 && <span className="mt-0.5 block text-2xs text-muted">{facts.join(" · ")}</span>}
        {capabilities.length > 0 && (
          <span className="mt-1 flex flex-wrap gap-1">
            {capabilities.map((label) => (
              <Tag key={label}>{label}</Tag>
            ))}
          </span>
        )}
      </td>
      <td className="border-t border-line py-2.5 pr-4">
        <LocationBadge location={model.location} />
        <span className="mt-0.5 block text-2xs text-faint">
          {model.provider ? `${model.provider} via ${model.backend}` : model.backend}
        </span>
      </td>
      <td className="border-t border-line py-2.5 pr-4">
        {model.modalities.length > 0 ? (
          model.modalities.map(titleCase).join(", ")
        ) : (
          <span className="text-faint" title="The backend's labels don't map to an Antar modality yet.">
            Unclassified
          </span>
        )}
      </td>
      <td className="border-t border-line py-2.5 pr-4 text-muted">
        {model.runtime ?? "—"}
        {model.quantization && <span className="block text-2xs text-faint">{model.quantization}</span>}
      </td>
      <td className="tabular border-t border-line py-2.5 pr-4 text-right text-muted">
        {formatBytes(model.size_bytes)}
        <span className="block text-2xs text-faint">
          {parameters ? `${parameters} parameters` : "parameters unknown"}
        </span>
        {model.context_length !== null && (
          <span className="block text-2xs text-faint">
            {model.context_length.toLocaleString("en-US")} context
          </span>
        )}
      </td>
      <td className="border-t border-line py-2.5 pr-4">
        <ModelState model={model} />
      </td>
      <td className="border-t border-line py-2.5 pr-5">
        <ModelActions model={model} download={download} />
      </td>
    </tr>
  );
}

function Inventory({ inventory }: { inventory: ModelInventory }) {
  const [params, setParams] = useSearchParams();
  const filters = parseFilters(params);
  const visible = filterModels(inventory.models, filters);
  const downloads = useDownloads();

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <>
      <ul className="mb-6 grid gap-3 sm:grid-cols-3">
        {inventory.sources.map((source) => (
          <li key={source.backend} className="rounded-lg border border-line bg-surface px-4 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium">{source.display_name}</span>
              <StatusPill availability={source.availability} />
            </div>
            <p className="mt-1 text-xs text-muted">
              {source.model_count > 0 ? `${source.model_count} models` : source.detail}
            </p>
          </li>
        ))}
      </ul>

      <ModelFilterBar filters={filters} sources={inventory.sources} onChange={setParam} />

      <Panel className="[&>div]:p-0">
        {visible.length === 0 ? (
          <p className="p-5 text-sm text-muted">
            No models match these filters. Clear a filter, or check that a backend is reachable in
            Settings.
          </p>
        ) : (
          <div className="relative overflow-x-auto">
            <table className="w-full min-w-[56rem] border-separate border-spacing-0 text-sm">
              <caption className="sr-only">Local and cloud models</caption>
              <thead className="text-left text-muted">
                <tr>
                  {["Model", "Runs on", "Modalities", "Runtime"].map((heading, index) => (
                    <th key={heading} scope="col" className={`py-3 pr-4 font-normal ${index === 0 ? "pl-5" : ""}`}>
                      {heading}
                    </th>
                  ))}
                  <th scope="col" className="py-3 pr-4 text-right font-normal">Size</th>
                  <th scope="col" className="py-3 pr-4 font-normal">State</th>
                  <th scope="col" className="py-3 pr-5 font-normal">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((model) => (
                  <ModelRow
                    key={modelKey(model)}
                    model={model}
                    download={downloads.data?.find((job) => job.model === model.id)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <p className="mt-3 text-xs text-faint">
        Showing {visible.length} of {inventory.models.length}. Sizes, parameter counts, and labels
        come from the backend or the model's published metadata; Antar does not estimate missing
        values, so a model without a published parameter count is listed under "Unknown size".
        Downloads start only when you confirm one.
      </p>
    </>
  );
}

export function Models() {
  const models = useModels();
  return (
    <>
      <PageHeader
        title="Models"
        summary="Every model your backends offer, local and cloud, with where each one runs and whether it is in memory. Load or download a local model here; cloud models are served as their server was started."
      />
      <QueryView query={models}>{(data) => <Inventory inventory={data} />}</QueryView>
    </>
  );
}
