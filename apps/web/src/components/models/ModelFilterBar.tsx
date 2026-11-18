import { titleCase } from "../../lib/format";
import { SIZE_BUCKETS } from "../../lib/models";
import type { ModelFilters } from "../../lib/models";
import { MODALITIES } from "../../lib/types";
import type { InventorySource } from "../../lib/types";

type Tone = "neutral" | "local" | "cloud";

const ACTIVE: Record<Tone, string> = {
  neutral: "border-ink/70 bg-raised text-ink",
  local: "border-local bg-local/10 text-ink",
  cloud: "border-cloud bg-cloud/10 text-ink",
};

interface ChipProps {
  active: boolean;
  tone?: Tone;
  onClick: () => void;
  children: string;
}

function Chip({ active, tone = "neutral", onClick, children }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-sm whitespace-nowrap transition-colors duration-150 ${
        active ? ACTIVE[tone] : "border-line text-muted hover:border-muted hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-2">
      <span className="w-20 shrink-0 text-xs text-faint">{label}</span>
      {children}
    </div>
  );
}

interface ModelFilterBarProps {
  filters: ModelFilters;
  sources: InventorySource[];
  /** Sets or clears one URL parameter. */
  onChange: (key: string, value: string | null) => void;
}

/** Every filter is a URL parameter, so a filtered catalog can be linked to. */
export function ModelFilterBar({ filters, sources, onChange }: ModelFilterBarProps) {
  const toggle = (key: string, current: string | null, value: string) =>
    onChange(key, current === value ? null : value);

  return (
    <div className="mb-4 space-y-2.5">
      <Group label="Runs on">
        <Chip active={!filters.location} onClick={() => onChange("location", null)}>
          Anywhere
        </Chip>
        <Chip
          tone="local"
          active={filters.location === "local"}
          onClick={() => toggle("location", filters.location, "local")}
        >
          Local
        </Chip>
        <Chip
          tone="cloud"
          active={filters.location === "cloud"}
          onClick={() => toggle("location", filters.location, "cloud")}
        >
          Cloud
        </Chip>
      </Group>

      <Group label="Modality">
        <Chip active={!filters.modality} onClick={() => onChange("modality", null)}>
          All
        </Chip>
        {MODALITIES.map((modality) => (
          <Chip
            key={modality}
            active={filters.modality === modality}
            onClick={() => toggle("modality", filters.modality, modality)}
          >
            {titleCase(modality)}
          </Chip>
        ))}
      </Group>

      <Group label="Parameters">
        <Chip active={!filters.size} onClick={() => onChange("size", null)}>
          Any size
        </Chip>
        {SIZE_BUCKETS.map((bucket) => (
          <Chip
            key={bucket.id}
            active={filters.size === bucket.id}
            onClick={() => toggle("size", filters.size, bucket.id)}
          >
            {bucket.label}
          </Chip>
        ))}
      </Group>

      <Group label="State">
        <Chip active={!filters.run} onClick={() => onChange("state", null)}>
          Any state
        </Chip>
        <Chip active={filters.run === "running"} onClick={() => toggle("state", filters.run, "running")}>
          Running
        </Chip>
        <Chip active={filters.run === "idle"} onClick={() => toggle("state", filters.run, "idle")}>
          Not running
        </Chip>
      </Group>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-1">
        <label className="flex items-center gap-2 text-sm text-muted">
          Backend
          <select
            value={filters.backend ?? ""}
            onChange={(event) => onChange("backend", event.target.value || null)}
            className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
          >
            <option value="">All backends</option>
            {sources.map((source) => (
              <option key={source.backend} value={source.backend}>
                {source.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted">
          <input
            type="checkbox"
            className="accent-(--color-ink)"
            checked={filters.downloadedOnly}
            onChange={(event) => onChange("downloaded", event.target.checked ? "1" : null)}
          />
          Downloaded only
        </label>
        <input
          type="search"
          aria-label="Search models"
          placeholder="Search by name, family, or label"
          value={filters.search}
          onChange={(event) => onChange("q", event.target.value || null)}
          className="w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm placeholder:text-faint sm:ml-auto sm:w-64"
        />
      </div>
    </div>
  );
}
