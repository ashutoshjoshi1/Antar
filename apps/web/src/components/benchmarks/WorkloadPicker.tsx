import { CODE_TESTS_WORKLOAD, splitWorkloads } from "../../lib/comparison";
import type { Workload } from "../../lib/types";
import { Notice, Tag } from "../ui";

interface WorkloadPickerProps {
  workloads: Workload[];
  selected: readonly string[];
  onChange: (selected: readonly string[]) => void;
  /** False when a selected model cannot take images. */
  visionAvailable: boolean;
  /** Shown on vision workloads when they are blocked. */
  visionReason: string;
  allowCode: boolean;
  onAllowCode: (allow: boolean) => void;
}

/** Workload ids that can actually run with the current models and switches. */
export function runnableWorkloads(
  workloads: Workload[],
  selected: readonly string[],
  visionAvailable: boolean,
  allowCode: boolean,
): string[] {
  return workloads
    .filter(
      (workload) =>
        selected.includes(workload.id) &&
        (visionAvailable || workload.modality !== "vision") &&
        (allowCode || workload.id !== CODE_TESTS_WORKLOAD),
    )
    .map((workload) => workload.id);
}

export function WorkloadPicker({ workloads, selected, onChange, visionAvailable, visionReason, allowCode, onAllowCode }: WorkloadPickerProps) {
  const groups = splitWorkloads(workloads);
  const hasCodeTests = workloads.some((workload) => workload.id === CODE_TESTS_WORKLOAD);

  const option = (workload: Workload) => {
    const needsVision = workload.modality === "vision" && !visionAvailable;
    const needsCode = workload.id === CODE_TESTS_WORKLOAD && !allowCode;
    const blocked = needsVision || needsCode;
    return (
      <label
        key={workload.id}
        className={`flex gap-3 rounded-md border border-line px-3 py-2.5 ${blocked ? "opacity-50" : "hover:border-muted"}`}
      >
        <input
          type="checkbox"
          className="mt-1 accent-(--color-ink)"
          disabled={blocked}
          checked={!blocked && selected.includes(workload.id)}
          onChange={(event) =>
            onChange(
              event.target.checked
                ? [...selected, workload.id]
                : selected.filter((id) => id !== workload.id),
            )
          }
        />
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2 text-sm">
            {workload.name}
            {needsVision && <Tag>{visionReason}</Tag>}
            {needsCode && <Tag>Needs code execution allowed</Tag>}
          </span>
          <span className="mt-0.5 block text-xs text-muted">
            {workload.prompts.length} prompts. {workload.description}
          </span>
        </span>
      </label>
    );
  };

  return (
    <div className="space-y-4">
      {groups.scored.length > 0 && (
        <fieldset>
          <legend className="mb-1.5 text-sm">
            Workloads scored automatically <span className="text-muted">against reference answers, by a fixed rule</span>
          </legend>
          <div className="grid gap-2 sm:grid-cols-2">{groups.scored.map(option)}</div>
        </fieldset>
      )}
      <fieldset>
        <legend className="mb-1.5 text-sm">
          Workloads for manual review <span className="text-muted">timed by Antar, read and scored by you</span>
        </legend>
        <div className="grid gap-2 sm:grid-cols-2">{groups.manual.map(option)}</div>
      </fieldset>
      {hasCodeTests && (
        <div>
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              className="mt-1 accent-(--color-ink)"
              checked={allowCode}
              onChange={(event) => onAllowCode(event.target.checked)}
            />
            Run model-written code to score the unit-tested coding workload
          </label>
          <div className="mt-2">
            <Notice>
              Off by default. The code a model writes runs on the machine running the Antar API, in
              a separate process with a time limit. That is not a security sandbox: only allow it
              for models and prompts you trust.
            </Notice>
          </div>
        </div>
      )}
    </div>
  );
}
