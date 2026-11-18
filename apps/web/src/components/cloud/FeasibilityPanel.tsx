import { useState } from "react";

import { useCloudCatalog, useCloudGpus, useFeasibility } from "../../lib/api";
import { BYTES_PER_GB, memoryBar } from "../../lib/cloud";
import { formatBytes, formatParameters } from "../../lib/format";
import type { FeasibilityEstimate, KnownModel, Verdict } from "../../lib/types";
import { buttonClass, fieldClass, Notice, Panel, QueryView, Tag } from "../ui";

const VERDICTS: Record<Verdict, { label: string; className: string; help: string }> = {
  fits: { label: "Fits", className: "text-ok", help: "Worth trying. Only a real load proves it." },
  tight: { label: "Tight", className: "text-warn", help: "Less than a tenth of the usable memory is left over." },
  does_not_fit: { label: "Does not fit", className: "text-down", help: "The request needs more than vLLM would reserve." },
};

// Neutral fills: lemon and periwinkle are reserved for where something runs.
const SEGMENT_FILLS = { weights: "bg-ink/80", kv_cache: "bg-ink/45", overhead: "bg-ink/20" } as const;

function Estimate({ estimate }: { estimate: FeasibilityEstimate }) {
  const bar = memoryBar(estimate);
  const verdict = VERDICTS[estimate.verdict];
  const over = estimate.headroom_bytes < 0;
  return (
    <div className="mt-5 space-y-4">
      <p className="text-sm">
        <span className={`font-medium ${verdict.className}`}>{verdict.label}.</span>{" "}
        <span className="text-muted">
          Needs {formatBytes(estimate.required_bytes)} of {formatBytes(estimate.usable_bytes)} usable (
          {formatBytes(estimate.total_bytes)} total), {over ? "short by" : "leaving"}{" "}
          {formatBytes(Math.abs(estimate.headroom_bytes))}. {verdict.help}
        </span>
      </p>

      <div>
        <div
          role="img"
          aria-label={`Memory required: ${bar.segments.map((segment) => `${segment.label} ${formatBytes(segment.bytes)}`).join(", ")}. Usable ${formatBytes(estimate.usable_bytes)}.`}
          className="relative h-5 overflow-hidden rounded bg-raised"
        >
          <div className="flex h-full">
            {bar.segments.map((segment) => (
              <div
                key={segment.key}
                className={`h-full border-r border-ground ${SEGMENT_FILLS[segment.key]}`}
                style={{ flexBasis: `${segment.fraction * 100}%` }}
              />
            ))}
          </div>
          <div
            aria-hidden
            className={`absolute inset-y-0 w-0.5 ${over ? "bg-down" : "bg-ok"}`}
            style={{ left: `${Math.min(bar.usableFraction, 1) * 100}%` }}
          />
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          {bar.segments.map((segment) => (
            <li key={segment.key} className="flex items-center gap-1.5">
              <span aria-hidden className={`size-2.5 rounded-sm ${SEGMENT_FILLS[segment.key]}`} />
              {segment.label} <span className="tabular text-ink">{formatBytes(segment.bytes)}</span>
            </li>
          ))}
          <li className="flex items-center gap-1.5">
            <span aria-hidden className={`h-3 w-0.5 ${over ? "bg-down" : "bg-ok"}`} />
            Usable limit <span className="tabular text-ink">{formatBytes(estimate.usable_bytes)}</span>
          </li>
        </ul>
      </div>

      <p className="tabular text-sm text-muted">
        Context {estimate.max_model_len.toLocaleString("en-US")} tokens, {estimate.concurrency} concurrent,{" "}
        {estimate.gpu_count} GPU{estimate.gpu_count === 1 ? "" : "s"}. KV cache is{" "}
        {formatBytes(estimate.kv_cache_bytes_per_token)} per token. At this context, up to{" "}
        {estimate.max_concurrency_at_full_context} sequences fit.
      </p>

      <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
        {estimate.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
    </div>
  );
}

const positive = (value: string) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
};

function Calculator({ models }: { models: KnownModel[] }) {
  const feasibility = useFeasibility();
  const gpus = useCloudGpus();
  const reading = gpus.data?.sample?.gpus[0]?.memory_total_bytes ?? null;
  const [modelId, setModelId] = useState(models[0]?.id ?? "");
  const [gpuCount, setGpuCount] = useState("1");
  // Null until the user types: the field then follows the GPU reading when there is one.
  const [typedMemory, setTypedMemory] = useState<string | null>(null);
  const [context, setContext] = useState("");
  const [concurrency, setConcurrency] = useState("1");

  const memoryGb = typedMemory ?? (reading !== null ? String(Math.round(reading / BYTES_PER_GB)) : "");
  const model = models.find((candidate) => candidate.id === modelId);
  const memory = positive(memoryGb);
  const count = positive(gpuCount);
  const sequences = positive(concurrency);
  const contextLength = context.trim() === "" ? null : positive(context);
  const valid = Boolean(model && memory && count && sequences && (context.trim() === "" || contextLength));

  const submit = () => {
    if (!model || !memory || !count || !sequences || !valid) return;
    feasibility.mutate({
      model: model.id,
      gpu_count: Math.round(count),
      gpu_memory_bytes: Math.round(memory * BYTES_PER_GB),
      max_model_len: contextLength === null ? null : Math.round(contextLength),
      concurrency: Math.round(sequences),
    });
  };

  return (
    <>
      <form
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="sm:col-span-2 lg:col-span-2">
          <label htmlFor="fit-model" className="mb-1.5 block text-sm">
            Catalog model
          </label>
          <select id="fit-model" className={fieldClass} value={modelId} onChange={(event) => setModelId(event.target.value)}>
            {models.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.id} ({formatParameters(candidate.parameter_count)}, {candidate.precision})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="fit-gpus" className="mb-1.5 block text-sm">
            GPU count
          </label>
          <input id="fit-gpus" type="number" min={1} max={16} className={fieldClass} value={gpuCount} onChange={(event) => setGpuCount(event.target.value)} />
        </div>
        <div>
          <label htmlFor="fit-memory" className="mb-1.5 block text-sm">
            Memory per GPU, GB
          </label>
          <input id="fit-memory" type="number" min={1} step="any" className={fieldClass} value={memoryGb} onChange={(event) => setTypedMemory(event.target.value)} />
        </div>
        <div>
          <label htmlFor="fit-concurrency" className="mb-1.5 block text-sm">
            Concurrent sequences
          </label>
          <input id="fit-concurrency" type="number" min={1} max={1024} className={fieldClass} value={concurrency} onChange={(event) => setConcurrency(event.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="fit-context" className="mb-1.5 block text-sm">
            Context length, tokens
          </label>
          <input
            id="fit-context"
            type="number"
            min={1}
            className={fieldClass}
            value={context}
            placeholder={model ? `Model maximum: ${model.context_length.toLocaleString("en-US")}` : ""}
            onChange={(event) => setContext(event.target.value)}
          />
        </div>
        <div className="flex items-end sm:col-span-2 lg:col-span-3">
          <button type="submit" disabled={!valid || feasibility.isPending} className={buttonClass}>
            {feasibility.isPending ? "Estimating…" : "Estimate memory"}
          </button>
        </div>
      </form>
      <p className="mt-3 text-xs text-faint">
        {reading !== null && typedMemory === null
          ? "Memory per GPU is prefilled from the first GPU's reading. "
          : "Enter the memory of one GPU; no GPU reading is available to prefill it. "}
        {model && `${model.name}: ${formatBytes(model.weights_bytes)} of weights, ${model.license}, revision ${model.revision.slice(0, 12)}.`}
      </p>
      {feasibility.isError && (
        <p role="alert" className="mt-3 text-sm text-down">
          {feasibility.error.message}
        </p>
      )}
      {feasibility.data && <Estimate estimate={feasibility.data} />}
    </>
  );
}

export function FeasibilityPanel() {
  const catalog = useCloudCatalog();
  return (
    <Panel title="Will it fit?" aside={<Tag>Approximate, arithmetic not measurement</Tag>}>
      <p className="mb-4 max-w-[75ch] text-sm text-muted">
        A memory budget for serving a catalog model with vLLM, worked out from the model's published
        file sizes and shape before anything is deployed.
      </p>
      <QueryView query={catalog}>
        {(models) =>
          models.length === 0 ? (
            <Notice tone="plain">The catalog is empty, so there is nothing to size.</Notice>
          ) : (
            <Calculator models={models} />
          )
        }
      </QueryView>
    </Panel>
  );
}
