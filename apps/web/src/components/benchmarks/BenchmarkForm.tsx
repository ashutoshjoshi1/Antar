import { useState } from "react";

import { useStartBenchmark } from "../../lib/api";
import type { BenchmarkConfig, LoadPolicy, ModelSpec, Workload } from "../../lib/types";
import { Tag } from "../ui";

const fieldClass = "w-full rounded-md border border-line bg-ground px-3 py-2 text-sm";

interface BenchmarkFormProps {
  models: ModelSpec[];
  workloads: Workload[];
  running: boolean;
}

const clamp = (value: string, min: number, max: number) =>
  Math.min(max, Math.max(min, Math.round(Number(value)) || min));

/** How many requests a configuration sends, mirroring the runner's own count. */
export function requestCount(
  workloads: Workload[],
  selected: readonly string[],
  warmup: number,
  runs: number,
  policy: LoadPolicy,
): number {
  const perWorkload = workloads
    .filter((workload) => selected.includes(workload.id))
    .reduce((total, workload) => total + warmup + runs * workload.prompts.length, 0);
  return perWorkload + (policy === "reload" && selected.length > 0 ? 1 : 0);
}

export function BenchmarkForm({ models, workloads, running }: BenchmarkFormProps) {
  const start = useStartBenchmark();
  const [modelId, setModelId] = useState(models[0]?.id ?? "");
  const [selected, setSelected] = useState<readonly string[]>(["general_qa"]);
  const [warmup, setWarmup] = useState(1);
  const [runs, setRuns] = useState(3);
  const [maxTokens, setMaxTokens] = useState(256);
  const [temperature, setTemperature] = useState(0);
  const [policy, setPolicy] = useState<LoadPolicy>("keep");

  const model = models.find((candidate) => candidate.id === modelId) ?? models[0];
  const hasVision = model?.modalities.includes("vision") ?? false;
  const usable = selected.filter(
    (id) => hasVision || workloads.find((workload) => workload.id === id)?.modality !== "vision",
  );
  const total = requestCount(workloads, usable, warmup, runs, policy);

  const submit = () => {
    if (!model || usable.length === 0) return;
    const config: BenchmarkConfig = {
      name: `${model.id} baseline`,
      model: { id: model.id },
      backend: model.backend,
      workloads: [...usable],
      warmup_runs: warmup,
      measured_runs: runs,
      max_tokens: maxTokens,
      temperature,
      seed: 42,
      enable_thinking: false,
      load_policy: policy,
    };
    start.mutate(config);
  };

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div>
        <label htmlFor="bench-model" className="mb-1.5 block text-sm">
          Model
        </label>
        <select id="bench-model" className={fieldClass} value={model?.id ?? ""} onChange={(event) => setModelId(event.target.value)}>
          {models.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {candidate.id}
              {candidate.quantization ? ` (${candidate.quantization})` : ""}
            </option>
          ))}
        </select>
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm">Workloads</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {workloads.map((workload) => {
            const blocked = workload.modality === "vision" && !hasVision;
            return (
              <label
                key={workload.id}
                className={`flex gap-3 rounded-md border border-line px-3 py-2.5 ${blocked ? "opacity-50" : "hover:border-muted"}`}
              >
                <input
                  type="checkbox"
                  className="mt-1 accent-(--color-local)"
                  disabled={blocked}
                  checked={!blocked && selected.includes(workload.id)}
                  onChange={(event) =>
                    setSelected(
                      event.target.checked
                        ? [...selected, workload.id]
                        : selected.filter((id) => id !== workload.id),
                    )
                  }
                />
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2 text-sm">
                    {workload.name}
                    {blocked && <Tag>Needs a vision model</Tag>}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted">
                    {workload.prompts.length} prompts. {workload.description}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <label htmlFor="bench-warmup" className="mb-1.5 block text-sm">
            Warm-up requests
          </label>
          <input id="bench-warmup" type="number" min={0} max={20} className={fieldClass} value={warmup} onChange={(event) => setWarmup(clamp(event.target.value, 0, 20))} />
        </div>
        <div>
          <label htmlFor="bench-runs" className="mb-1.5 block text-sm">
            Measured passes
          </label>
          <input id="bench-runs" type="number" min={1} max={100} className={fieldClass} value={runs} onChange={(event) => setRuns(clamp(event.target.value, 1, 100))} />
        </div>
        <div>
          <label htmlFor="bench-tokens" className="mb-1.5 block text-sm">
            Maximum output tokens
          </label>
          <input id="bench-tokens" type="number" min={1} max={16384} className={fieldClass} value={maxTokens} onChange={(event) => setMaxTokens(clamp(event.target.value, 1, 16384))} />
        </div>
        <div>
          <label htmlFor="bench-temperature" className="mb-1.5 block text-sm">
            Temperature
          </label>
          <input
            id="bench-temperature"
            type="number"
            min={0}
            max={2}
            step={0.1}
            className={fieldClass}
            value={temperature}
            onChange={(event) => setTemperature(Math.min(2, Math.max(0, Number(event.target.value) || 0)))}
          />
        </div>
      </div>

      <fieldset>
        <legend className="mb-1.5 text-sm">Model loading</legend>
        <div className="space-y-1.5 text-sm">
          {(
            [
              ["keep", "Use the model as it is", "Loads it only if it is not in memory."],
              ["reload", "Reload first", "Unloads and reloads to measure load time and a cold first request."],
            ] as const
          ).map(([value, label, help]) => (
            <label key={value} className="flex items-baseline gap-2">
              <input type="radio" name="policy" className="accent-(--color-local)" checked={policy === value} onChange={() => setPolicy(value)} />
              <span>
                {label} <span className="text-muted">{help}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="submit"
          disabled={running || start.isPending || usable.length === 0 || !model}
          className="rounded-md bg-local px-4 py-2 text-sm font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {running ? "Benchmark running" : "Start benchmark"}
        </button>
        <p className="text-sm text-muted">
          {usable.length === 0
            ? "Choose at least one workload."
            : `${total} requests, one at a time. Reasoning is off and the seed is fixed so runs are comparable.`}
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
