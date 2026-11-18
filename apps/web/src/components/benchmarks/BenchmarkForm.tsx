import { useState } from "react";

import { useStartBenchmark } from "../../lib/api";
import { groupByLocation, modelKey } from "../../lib/models";
import type { BenchmarkConfig, LoadPolicy, ModelSpec, Workload } from "../../lib/types";
import { CloudConfirm } from "../CloudConfirm";
import { fieldClass, LocationBadge } from "../ui";
import { runnableWorkloads, WorkloadPicker } from "./WorkloadPicker";

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
  const [selectedKey, setSelectedKey] = useState(models[0] ? modelKey(models[0]) : "");
  const [allowCode, setAllowCode] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [selected, setSelected] = useState<readonly string[]>(["general_qa"]);
  const [warmup, setWarmup] = useState(1);
  const [runs, setRuns] = useState(3);
  const [maxTokens, setMaxTokens] = useState(256);
  const [temperature, setTemperature] = useState(0);
  const [policy, setPolicy] = useState<LoadPolicy>("keep");

  const model = models.find((candidate) => modelKey(candidate) === selectedKey) ?? models[0];
  const cloud = model?.location === "cloud";
  const hasVision = model?.modalities.includes("vision") ?? false;
  const usable = runnableWorkloads(workloads, selected, hasVision, allowCode);
  const total = requestCount(workloads, usable, warmup, runs, cloud ? "keep" : policy);

  const submit = (confirmedCloud: boolean) => {
    if (!model || usable.length === 0) return;
    // A cloud run uses paid instance time, so it waits for an explicit confirmation.
    if (cloud && !confirmedCloud) {
      setConfirming(true);
      return;
    }
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
      // A cloud server serves what it was started with; Antar cannot reload it.
      load_policy: cloud ? "keep" : policy,
      allow_code_execution: allowCode && usable.includes("code_tests"),
      // Never sent for a local model.
      ...(cloud && { confirm_cloud_usage: true }),
    };
    start.mutate(config, { onSettled: () => setConfirming(false) });
  };

  return (
    <form
      className="space-y-5"
      onSubmit={(event) => {
        event.preventDefault();
        submit(false);
      }}
    >
      <div>
        <label htmlFor="bench-model" className="mb-1.5 block text-sm">
          Model
        </label>
        <select
          id="bench-model"
          className={fieldClass}
          value={model ? modelKey(model) : ""}
          onChange={(event) => {
            setSelectedKey(event.target.value);
            setConfirming(false);
          }}
        >
          {groupByLocation(models).map((group) => (
            <optgroup key={group.label} label={group.label}>
              {group.models.map((candidate) => (
                <option key={modelKey(candidate)} value={modelKey(candidate)}>
                  {candidate.id}
                  {candidate.quantization ? ` (${candidate.quantization})` : ""}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {model && (
          <p className="mt-2">
            <LocationBadge location={model.location} detail={model.provider} />
          </p>
        )}
      </div>

      <WorkloadPicker
        workloads={workloads}
        selected={selected}
        onChange={setSelected}
        visionAvailable={hasVision}
        visionReason="Needs a vision model"
        allowCode={allowCode}
        onAllowCode={setAllowCode}
      />

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
              <input type="radio" name="policy" className="accent-(--color-local)" disabled={cloud && value === "reload"} checked={cloud ? value === "keep" : policy === value} onChange={() => setPolicy(value)} />
              <span>
                {label} <span className="text-muted">{help}</span>
              </span>
            </label>
          ))}
        </div>
        {cloud && (
          <p className="mt-1.5 text-xs text-muted">
            Reloading is not offered for cloud models: the server keeps the model it was started with.
          </p>
        )}
      </fieldset>

      {confirming && cloud && (
        <CloudConfirm
          subject="This benchmark"
          detail={`${total} requests to ${model?.id ?? "the cloud model"}, one at a time.`}
          pending={start.isPending}
          onConfirm={() => submit(true)}
          onCancel={() => setConfirming(false)}
        />
      )}

      <div className="flex flex-wrap items-center gap-4">
        <button
          type="submit"
          disabled={running || start.isPending || confirming || usable.length === 0 || !model}
          className={`rounded-md px-4 py-2 text-sm font-medium text-ground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 ${cloud ? "bg-cloud" : "bg-local"}`}
        >
          {running ? "Benchmark running" : cloud ? "Start benchmark…" : "Start benchmark"}
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
