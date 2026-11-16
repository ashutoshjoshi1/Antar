import { useState } from "react";

import { NotBuiltYet, PageHeader, Panel, QueryView, Tag } from "../components/ui";
import { useCapabilities, useModels } from "../lib/api";
import { titleCase } from "../lib/format";
import type { Capabilities, ModelSpec, TechniqueApplicability } from "../lib/types";

interface Draft {
  modelKey: string;
  techniques: readonly string[];
  maxMemoryGb: string;
  maxQualityDrop: string;
}

interface JobPreview {
  name: string;
  model: { id: string; revision: string | null };
  modality: string;
  task: string;
  techniques: { technique: string }[];
  constraints: { max_memory_gb?: number; max_quality_drop?: number };
  execution_backend: string;
  target_backend: string;
}

const positive = (value: string): number | undefined => {
  const parsed = Number(value);
  return value !== "" && Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
};

/** Builds the OptimizationJob document the API will accept once execution exists. */
export function buildJobPreview(model: ModelSpec, draft: Draft): JobPreview | null {
  const [modality] = model.modalities;
  const [task] = model.tasks;
  if (!modality || !task || draft.techniques.length === 0) return null;
  const maxMemory = positive(draft.maxMemoryGb);
  // Zero is meaningful here: it means no quality drop is acceptable.
  const dropPercent = draft.maxQualityDrop === "0" ? 0 : positive(draft.maxQualityDrop);
  return {
    name: `optimize-${model.id.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}`,
    model: { id: model.id, revision: model.revision },
    modality,
    task,
    techniques: draft.techniques.map((technique) => ({ technique })),
    constraints: {
      ...(maxMemory !== undefined && { max_memory_gb: maxMemory }),
      ...(dropPercent !== undefined && dropPercent <= 100 && { max_quality_drop: dropPercent / 100 }),
    },
    execution_backend: "amd_cloud",
    target_backend: model.backend,
  };
}

const inputClass =
  "w-full rounded-md border border-line bg-ground px-3 py-2 text-sm placeholder:text-faint";

function TechniqueOption({
  entry,
  checked,
  onToggle,
}: {
  entry: TechniqueApplicability;
  checked: boolean;
  onToggle: () => void;
}) {
  const unusable = entry.applicability === "not_applicable";
  return (
    <label className={`flex gap-3 rounded-md border border-line px-3 py-2.5 ${unusable ? "opacity-50" : "hover:border-muted"}`}>
      <input
        type="checkbox"
        className="mt-1 accent-(--color-local)"
        checked={checked && !unusable}
        disabled={unusable}
        onChange={onToggle}
      />
      <span className="min-w-0">
        <span className="flex flex-wrap items-center gap-2 text-sm">
          {titleCase(entry.technique)}
          {entry.applicability !== "candidate" && (
            <Tag tone={unusable ? "plain" : "warn"}>{titleCase(entry.applicability)}</Tag>
          )}
        </span>
        <span className="mt-0.5 block text-xs text-muted">{entry.note}</span>
      </span>
    </label>
  );
}

function Configurator({ models, capabilities }: { models: ModelSpec[]; capabilities: Capabilities }) {
  const candidates = models.filter((model) => !model.simulated && model.modalities.length > 0);
  const [draft, setDraft] = useState<Draft>({
    modelKey: "",
    techniques: [],
    maxMemoryGb: "",
    maxQualityDrop: "",
  });
  const model = candidates.find((candidate) => `${candidate.backend}:${candidate.id}` === draft.modelKey);
  const modality = model?.modalities[0];
  const techniques = capabilities.techniques.filter((entry) => entry.modality === modality);
  const preview = model ? buildJobPreview(model, draft) : null;

  const toggle = (technique: string) =>
    setDraft((current) => ({
      ...current,
      techniques: current.techniques.includes(technique)
        ? current.techniques.filter((name) => name !== technique)
        : [...current.techniques, technique],
    }));

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
      <Panel title="Configure a job">
        <form className="space-y-6" onSubmit={(event) => event.preventDefault()}>
          <div>
            <label htmlFor="model" className="mb-1.5 block text-sm">
              Model
            </label>
            <select
              id="model"
              className={inputClass}
              value={draft.modelKey}
              onChange={(event) => setDraft({ ...draft, modelKey: event.target.value, techniques: [] })}
            >
              <option value="">
                {candidates.length > 0 ? "Choose a discovered model" : "No models discovered yet"}
              </option>
              {candidates.map((candidate) => (
                <option key={`${candidate.backend}:${candidate.id}`} value={`${candidate.backend}:${candidate.id}`}>
                  {candidate.id} ({candidate.modalities.join(", ")})
                </option>
              ))}
            </select>
          </div>

          <fieldset disabled={!model}>
            <legend className="mb-1.5 text-sm">
              Techniques{modality && <span className="text-muted"> for {modality} models</span>}
            </legend>
            {model ? (
              <div className="grid gap-2 sm:grid-cols-2">
                {techniques.map((entry) => (
                  <TechniqueOption
                    key={entry.technique}
                    entry={entry}
                    checked={draft.techniques.includes(entry.technique)}
                    onToggle={() => toggle(entry.technique)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">Choose a model to see which techniques apply to it.</p>
            )}
          </fieldset>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="max-memory" className="mb-1.5 block text-sm">
                Memory limit on the target, GB
              </label>
              <input
                id="max-memory"
                type="number"
                min="0"
                step="0.5"
                inputMode="decimal"
                placeholder="No limit"
                className={inputClass}
                value={draft.maxMemoryGb}
                onChange={(event) => setDraft({ ...draft, maxMemoryGb: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="max-drop" className="mb-1.5 block text-sm">
                Largest acceptable quality drop, %
              </label>
              <input
                id="max-drop"
                type="number"
                min="0"
                max="100"
                step="1"
                inputMode="decimal"
                placeholder="No limit"
                className={inputClass}
                value={draft.maxQualityDrop}
                onChange={(event) => setDraft({ ...draft, maxQualityDrop: event.target.value })}
              />
            </div>
          </div>

          <div>
            <button
              type="submit"
              disabled
              aria-describedby="run-help"
              className="cursor-not-allowed rounded-md border border-line bg-raised px-4 py-2 text-sm text-faint"
            >
              Run optimization
            </button>
            <p id="run-help" className="mt-2 text-xs text-muted">
              Running jobs is not built yet. Copy the specification on the right to validate
              it against the <code className="font-mono">OptimizationJob</code> schema.
            </p>
          </div>
        </form>
      </Panel>

      <Panel title="Job specification" aside={<Tag>Draft, never submitted</Tag>}>
        {preview ? (
          <pre className="overflow-x-auto font-mono text-xs leading-relaxed text-muted">
            {JSON.stringify(preview, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-muted">
            Choose a model and at least one technique to see the job specification.
          </p>
        )}
      </Panel>
    </div>
  );
}

export function Optimization() {
  const models = useModels();
  const capabilities = useCapabilities();
  return (
    <>
      <PageHeader
        title="Optimization"
        summary="Describe what to optimize and the limits the result must meet. Antar checks which techniques make sense for the model's modality."
      />
      <NotBuiltYet>
        No optimization technique can be executed yet: no fine-tuning, distillation, or quantization
        runs from here, and nothing is sent to a cloud GPU. This page builds and checks a job
        specification only.
      </NotBuiltYet>
      <QueryView query={models}>
        {(inventory) => (
          <QueryView query={capabilities}>
            {(data) => <Configurator models={inventory.models} capabilities={data} />}
          </QueryView>
        )}
      </QueryView>
    </>
  );
}
