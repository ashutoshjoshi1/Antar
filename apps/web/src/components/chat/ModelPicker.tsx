import { formatBytes } from "../../lib/format";
import { groupByLocation, modelKey } from "../../lib/models";
import type { ModelSpec } from "../../lib/types";
import { fieldClass, LocationBadge, Panel } from "../ui";

interface ModelPickerProps {
  models: ModelSpec[];
  model: ModelSpec | undefined;
  disabled: boolean;
  onChange: (key: string) => void;
}

/** One selector for every backend's models, grouped by where they run. */
export function ModelPicker({ models, model, disabled, onChange }: ModelPickerProps) {
  const details = model
    ? [model.quantization, model.size_bytes !== null && formatBytes(model.size_bytes), model.runtime].filter(Boolean)
    : [];
  return (
    <Panel title="Model" aside={model && <LocationBadge location={model.location} detail={model.provider} />}>
      <label htmlFor="model" className="sr-only">
        Model
      </label>
      <select
        id="model"
        value={model ? modelKey(model) : ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className={fieldClass}
      >
        {groupByLocation(models).map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.models.map((candidate) => (
              <option key={modelKey(candidate)} value={modelKey(candidate)}>
                {candidate.id}
                {candidate.loaded ? " (loaded)" : ""}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {model && (
        <p className="mt-2 text-xs text-muted">
          {details.join(", ")}
          {details.length > 0 && ". "}
          {model.location === "cloud"
            ? "Requests leave this machine for the cloud endpoint, through the Antar API."
            : model.loaded === false
              ? "Not in memory yet, so the first reply includes load time."
              : "Runs on this machine."}
        </p>
      )}
    </Panel>
  );
}
