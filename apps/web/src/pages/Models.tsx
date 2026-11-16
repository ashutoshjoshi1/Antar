import { useState } from "react";
import { useSearchParams } from "react-router";

import { PageHeader, Panel, QueryView, StatusPill, Tag } from "../components/ui";
import { useDownloads, useModelAction, useModels } from "../lib/api";
import { formatBytes, titleCase } from "../lib/format";
import { MODALITIES } from "../lib/types";
import type { DownloadJob, Modality, ModelInventory, ModelSpec } from "../lib/types";

interface Filters {
  modality: Modality | null;
  search: string;
  downloadedOnly: boolean;
}

export function filterModels(models: ModelSpec[], filters: Filters): ModelSpec[] {
  const needle = filters.search.trim().toLowerCase();
  const rank = (model: ModelSpec) => (model.loaded ? 0 : model.downloaded ? 1 : 2);
  return [...models].sort((a, b) => rank(a) - rank(b)).filter(
    (model) =>
      (!filters.modality || model.modalities.includes(filters.modality)) &&
      (!filters.downloadedOnly || model.downloaded === true) &&
      (!needle ||
        model.id.toLowerCase().includes(needle) ||
        model.labels.some((label) => label.toLowerCase().includes(needle))),
  );
}

function isModality(value: string | null): value is Modality {
  return MODALITIES.some((modality) => modality === value);
}

function chipClass(active: boolean): string {
  return `rounded-full border px-3 py-1 text-sm transition-colors duration-150 ${
    active ? "border-local bg-local/10 text-ink" : "border-line text-muted hover:border-muted hover:text-ink"
  }`;
}

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

function ModelRow({ model, download }: ModelRowProps) {
  const capabilities = model.labels.filter((label) =>
    ["reasoning", "tool-calling", "vision", "coding"].includes(label),
  );
  return (
    <tr className="align-top hover:bg-raised/40">
      <td className="border-t border-line py-2.5 pr-4 pl-5">
        <span className="font-mono text-[0.8125rem] break-all">{model.id}</span>
        {model.checkpoint && (
          <span className="mt-0.5 block font-mono text-2xs break-all text-faint">{model.checkpoint}</span>
        )}
        {capabilities.length > 0 && (
          <span className="mt-1 flex flex-wrap gap-1">
            {capabilities.map((label) => (
              <Tag key={label}>{label}</Tag>
            ))}
          </span>
        )}
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
      </td>
      <td className="border-t border-line py-2.5 pr-4">
        {model.simulated ? (
          <Tag tone="warn">Simulated</Tag>
        ) : model.loaded ? (
          <span className="text-local">Loaded</span>
        ) : model.downloaded ? (
          <span className="text-ok">Downloaded</span>
        ) : model.downloaded === false ? (
          <span className="text-faint">In catalog</span>
        ) : (
          <span className="text-faint">Unknown</span>
        )}
      </td>
      <td className="border-t border-line py-2.5 pr-5">
        <ModelActions model={model} download={download} />
      </td>
    </tr>
  );
}

function Inventory({ inventory }: { inventory: ModelInventory }) {
  const [params, setParams] = useSearchParams();
  const modalityParam = params.get("modality");
  const filters: Filters = {
    modality: isModality(modalityParam) ? modalityParam : null,
    search: params.get("q") ?? "",
    downloadedOnly: params.get("downloaded") === "1",
  };
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

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button type="button" aria-pressed={!filters.modality} className={chipClass(!filters.modality)} onClick={() => setParam("modality", null)}>
          All
        </button>
        {MODALITIES.map((modality) => (
          <button
            key={modality}
            type="button"
            aria-pressed={filters.modality === modality}
            className={chipClass(filters.modality === modality)}
            onClick={() => setParam("modality", filters.modality === modality ? null : modality)}
          >
            {titleCase(modality)}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            className="accent-(--color-local)"
            checked={filters.downloadedOnly}
            onChange={(event) => setParam("downloaded", event.target.checked ? "1" : null)}
          />
          Downloaded only
        </label>
        <input
          type="search"
          aria-label="Search models"
          placeholder="Search by name or label"
          value={filters.search}
          onChange={(event) => setParam("q", event.target.value || null)}
          className="w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm placeholder:text-faint sm:w-60"
        />
      </div>

      <Panel className="[&>div]:p-0">
        {visible.length === 0 ? (
          <p className="p-5 text-sm text-muted">
            No models match these filters. Clear a filter, or check that a backend is reachable in
            Settings.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[46rem] border-separate border-spacing-0 text-sm">
              <caption className="sr-only">Discovered models</caption>
              <thead className="text-left text-muted">
                <tr>
                  {["Model", "Modalities", "Runtime"].map((heading, index) => (
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
                    key={`${model.backend}:${model.id}`}
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
        Showing {visible.length} of {inventory.models.length}. Sizes and labels are reported by the
        backend; Antar does not estimate missing values. Downloads start only when you confirm one.
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
        summary="Every model Lemonade offers, with what is downloaded and what is in memory. Load a downloaded model, or download one after confirming its size."
      />
      <QueryView query={models}>{(data) => <Inventory inventory={data} />}</QueryView>
    </>
  );
}
