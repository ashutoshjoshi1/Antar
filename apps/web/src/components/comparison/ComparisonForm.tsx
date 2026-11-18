import { useState } from "react";

import { useStartComparison } from "../../lib/api";
import { comparisonRequestCount, sideCandidates } from "../../lib/comparison";
import { modelKey } from "../../lib/models";
import type { ComparisonConfig, ModelSpec, Workload } from "../../lib/types";
import { runnableWorkloads, WorkloadPicker } from "../benchmarks/WorkloadPicker";
import { CloudConfirm } from "../CloudConfirm";
import { fieldClass, LocationBadge, Notice, primaryButtonClass, Tag } from "../ui";

const clamp = (value: string, min: number, max: number) =>
  Math.min(max, Math.max(min, Math.round(Number(value)) || min));

const MAX_BUDGET_MINUTES = 24 * 60;
const DEFAULT_WORKLOAD = "qa_exact";

interface SideSelectProps {
  id: string;
  label: string;
  side: "local" | "cloud";
  models: ModelSpec[];
  value: string;
  onChange: (key: string) => void;
}

function SideSelect({ id, label, side, models, value, onChange }: SideSelectProps) {
  const model = models.find((candidate) => modelKey(candidate) === value);
  return (
    <div className={`rounded-md border-l-2 pl-3 ${side === "local" ? "border-local" : "border-cloud"}`}>
      <label htmlFor={id} className="mb-1.5 flex items-center justify-between gap-2 text-sm">
        {label}
        <LocationBadge location={side} />
      </label>
      <select id={id} className={fieldClass} value={value} onChange={(event) => onChange(event.target.value)}>
        {models.map((candidate) => (
          <option key={modelKey(candidate)} value={modelKey(candidate)}>
            {candidate.id}
            {candidate.simulated ? " (simulated)" : candidate.quantization ? ` (${candidate.quantization})` : ""}
          </option>
        ))}
      </select>
      {model && (
        <p className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
          {model.provider && model.provider !== model.backend ? `${model.provider} via ${model.backend}` : model.backend}
          {model.simulated && <Tag tone="warn">Simulated</Tag>}
        </p>
      )}
    </div>
  );
}

interface ComparisonFormProps {
  models: ModelSpec[];
  workloads: Workload[];
  /** The configured experiment limit, used when no budget is typed. */
  defaultBudgetMinutes: number;
  running: boolean;
}

const preferred = (models: ModelSpec[]) => models.find((model) => !model.simulated) ?? models[0];

export function ComparisonForm({ models, workloads, defaultBudgetMinutes, running }: ComparisonFormProps) {
  const start = useStartComparison();
  const sides = sideCandidates(models);
  const firstLocal = preferred(sides.local);
  const firstCloud = preferred(sides.cloud);
  const [localKey, setLocalKey] = useState(firstLocal ? modelKey(firstLocal) : "");
  const [cloudKey, setCloudKey] = useState(firstCloud ? modelKey(firstCloud) : "");
  const [selected, setSelected] = useState<readonly string[]>(
    workloads.some((workload) => workload.id === DEFAULT_WORKLOAD) ? [DEFAULT_WORKLOAD] : workloads.slice(0, 1).map((workload) => workload.id),
  );
  const [allowCode, setAllowCode] = useState(false);
  const [warmup, setWarmup] = useState(1);
  const [runs, setRuns] = useState(3);
  const [maxTokens, setMaxTokens] = useState(256);
  const [temperature, setTemperature] = useState(0);
  const [seed, setSeed] = useState("42");
  const [thinking, setThinking] = useState(false);
  const [budget, setBudget] = useState(String(defaultBudgetMinutes));
  const [confirming, setConfirming] = useState(false);

  const local = sides.local.find((model) => modelKey(model) === localKey) ?? firstLocal;
  const cloud = sides.cloud.find((model) => modelKey(model) === cloudKey) ?? firstCloud;

  if (!local || !cloud) {
    return (
      <div className="text-sm">
        <p className="font-medium">A comparison needs one model on each side</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-muted">
          {!local && <li>No local chat model is downloaded. Download one on the Models page.</li>}
          {!cloud && (
            <li>
              No cloud model is being served. Check the connection on the AMD Cloud page. For
              offline development, turn the mock backend on; its results are labelled Simulated.
            </li>
          )}
        </ul>
      </div>
    );
  }

  const simulated = local.simulated || cloud.simulated;
  const bothVision = local.modalities.includes("vision") && cloud.modalities.includes("vision");
  const usable = runnableWorkloads(workloads, selected, bothVision, allowCode);
  const total = comparisonRequestCount(workloads, usable, warmup, runs);
  const budgetMinutes = Number(budget);
  const budgetValid = Number.isFinite(budgetMinutes) && budgetMinutes > 0 && budgetMinutes <= MAX_BUDGET_MINUTES;
  const seedValue = seed.trim() === "" ? null : Math.max(0, Math.round(Number(seed)) || 0);
  const ready = usable.length > 0 && budgetValid && !running;

  const submit = () => {
    const config: ComparisonConfig = {
      name: `${local.id} vs ${cloud.id}`.slice(0, 120),
      local: { backend: local.backend, model: { id: local.id } },
      cloud: { backend: cloud.backend, model: { id: cloud.id } },
      workloads: usable,
      warmup_runs: warmup,
      measured_runs: runs,
      max_tokens: maxTokens,
      temperature,
      seed: seedValue,
      enable_thinking: thinking,
      allow_code_execution: allowCode && usable.includes("code_tests"),
      time_budget_minutes: budgetMinutes,
    };
    start.mutate(config, { onSettled: () => setConfirming(false) });
  };

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        // Submitting only opens the confirmation; nothing is sent from here.
        if (ready) setConfirming(true);
      }}
    >
      {simulated && (
        <Notice title="Simulated">
          At least one side is a mock backend. It produces placeholder text and no real inference,
          so this comparison and everything in its report will be labelled Simulated.
        </Notice>
      )}

      <div className="grid gap-5 md:grid-cols-2">
        <SideSelect id="cmp-local" label="Local model" side="local" models={sides.local} value={modelKey(local)} onChange={setLocalKey} />
        <SideSelect id="cmp-cloud" label="Cloud model" side="cloud" models={sides.cloud} value={modelKey(cloud)} onChange={setCloudKey} />
      </div>

      <WorkloadPicker
        workloads={workloads}
        selected={selected}
        onChange={setSelected}
        visionAvailable={bothVision}
        visionReason="Needs vision on both models"
        allowCode={allowCode}
        onAllowCode={setAllowCode}
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div>
          <label htmlFor="cmp-warmup" className="mb-1.5 block text-sm">
            Warm-up requests
          </label>
          <input id="cmp-warmup" type="number" min={0} max={20} className={fieldClass} value={warmup} onChange={(event) => setWarmup(clamp(event.target.value, 0, 20))} />
        </div>
        <div>
          <label htmlFor="cmp-runs" className="mb-1.5 block text-sm">
            Measured passes
          </label>
          <input id="cmp-runs" type="number" min={1} max={100} className={fieldClass} value={runs} onChange={(event) => setRuns(clamp(event.target.value, 1, 100))} />
        </div>
        <div>
          <label htmlFor="cmp-tokens" className="mb-1.5 block text-sm">
            Maximum output tokens
          </label>
          <input id="cmp-tokens" type="number" min={1} max={16384} className={fieldClass} value={maxTokens} onChange={(event) => setMaxTokens(clamp(event.target.value, 1, 16384))} />
        </div>
        <div>
          <label htmlFor="cmp-temperature" className="mb-1.5 block text-sm">
            Temperature
          </label>
          <input
            id="cmp-temperature"
            type="number"
            min={0}
            max={2}
            step={0.1}
            className={fieldClass}
            value={temperature}
            onChange={(event) => setTemperature(Math.min(2, Math.max(0, Number(event.target.value) || 0)))}
          />
        </div>
        <div>
          <label htmlFor="cmp-seed" className="mb-1.5 block text-sm">
            Seed <span className="text-muted">(blank for none)</span>
          </label>
          <input id="cmp-seed" type="number" min={0} className={fieldClass} value={seed} onChange={(event) => setSeed(event.target.value)} />
        </div>
        <div>
          <label htmlFor="cmp-budget" className="mb-1.5 block text-sm">
            Time budget, minutes
          </label>
          <input id="cmp-budget" type="number" min={1} max={MAX_BUDGET_MINUTES} step="any" className={fieldClass} value={budget} aria-invalid={!budgetValid} onChange={(event) => setBudget(event.target.value)} />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="accent-(--color-ink)" checked={thinking} onChange={(event) => setThinking(event.target.checked)} />
        Let the models reason first
        <span className="text-muted">Off keeps output length comparable.</span>
      </label>

      {confirming && (
        <CloudConfirm
          subject="This comparison"
          simulated={cloud.simulated}
          detail={`${total} requests in all, the local side first, then the cloud side. It stops itself after ${budgetMinutes} minutes.`}
          pending={start.isPending}
          onConfirm={submit}
          onCancel={() => setConfirming(false)}
        />
      )}

      <div className="flex flex-wrap items-center gap-4">
        <button type="submit" disabled={!ready || confirming || start.isPending} className={primaryButtonClass}>
          {running ? "Comparison running" : "Start comparison…"}
        </button>
        <p className="text-sm text-muted">
          {usable.length === 0
            ? "Choose at least one workload."
            : !budgetValid
              ? "Enter a time budget between 1 minute and 24 hours."
              : `${total} requests, one at a time: ${total / 2} per side with identical settings.`}
        </p>
      </div>
      {start.isError && (
        <p role="alert" className="text-sm text-down">
          {start.error.message}
        </p>
      )}
    </form>
  );
}
