import { MODALITIES } from "./types";
import type { ExecutionLocation, Modality, ModelSpec } from "./types";

export type SizeBucket = "small" | "medium" | "large" | "unknown";
export type RunFilter = "running" | "idle";
export type LocationFilter = Exclude<ExecutionLocation, "mock">;

const BILLION = 1_000_000_000;
const SMALL_BELOW = 4 * BILLION;
const LARGE_FROM = 16 * BILLION;

export const SIZE_BUCKETS: readonly { id: SizeBucket; label: string }[] = [
  { id: "small", label: "Under 4B" },
  { id: "medium", label: "4B to 16B" },
  { id: "large", label: "16B and up" },
  { id: "unknown", label: "Unknown size" },
];

/** Buckets by the published parameter count only. A model without one is "unknown", never guessed. */
export function sizeBucket(model: Pick<ModelSpec, "parameter_count">): SizeBucket {
  const count = model.parameter_count;
  if (count === null || count === undefined) return "unknown";
  if (count < SMALL_BELOW) return "small";
  return count < LARGE_FROM ? "medium" : "large";
}

/** In memory and able to answer now, as far as the backend reports. */
export function isRunning(model: Pick<ModelSpec, "state" | "loaded">): boolean {
  return model.state === "loaded" || model.loaded === true;
}

export interface ModelFilters {
  modality: Modality | null;
  search: string;
  downloadedOnly: boolean;
  location: LocationFilter | null;
  size: SizeBucket | null;
  run: RunFilter | null;
  backend: string | null;
}

export const NO_FILTERS: ModelFilters = {
  modality: null,
  search: "",
  downloadedOnly: false,
  location: null,
  size: null,
  run: null,
  backend: null,
};

function oneOf<T extends string>(value: string | null, allowed: readonly T[]): T | null {
  return allowed.find((item) => item === value) ?? null;
}

/** Filters live in the URL so a filtered view can be shared. Unknown values are ignored. */
export function parseFilters(params: URLSearchParams): ModelFilters {
  return {
    modality: oneOf(params.get("modality"), MODALITIES),
    search: params.get("q") ?? "",
    downloadedOnly: params.get("downloaded") === "1",
    location: oneOf(params.get("location"), ["local", "cloud"] as const),
    size: oneOf(
      params.get("size"),
      SIZE_BUCKETS.map((bucket) => bucket.id),
    ),
    run: oneOf(params.get("state"), ["running", "idle"] as const),
    backend: params.get("backend") || null,
  };
}

export function filterModels(models: ModelSpec[], filters: ModelFilters): ModelSpec[] {
  const needle = filters.search.trim().toLowerCase();
  const rank = (model: ModelSpec) => (isRunning(model) ? 0 : model.downloaded ? 1 : 2);
  return [...models]
    .sort((a, b) => rank(a) - rank(b))
    .filter(
      (model) =>
        (!filters.modality || model.modalities.includes(filters.modality)) &&
        (!filters.downloadedOnly || model.downloaded === true) &&
        (!filters.location || model.location === filters.location) &&
        (!filters.size || sizeBucket(model) === filters.size) &&
        (!filters.run || isRunning(model) === (filters.run === "running")) &&
        (!filters.backend || model.backend === filters.backend) &&
        (!needle ||
          model.id.toLowerCase().includes(needle) ||
          (model.family?.toLowerCase().includes(needle) ?? false) ||
          model.labels.some((label) => label.toLowerCase().includes(needle))),
    );
}

/** A model id is only unique within its backend. */
export function modelKey(model: Pick<ModelSpec, "backend" | "id">): string {
  return `${model.backend}:${model.id}`;
}

export interface LocationGroup {
  location: ExecutionLocation | null;
  label: string;
  models: ModelSpec[];
}

const GROUPS: readonly { location: ExecutionLocation | null; label: string }[] = [
  { location: "local", label: "Local" },
  { location: "cloud", label: "Cloud" },
  { location: "mock", label: "Simulated" },
  { location: null, label: "Location not reported" },
];

/** Models grouped by where they run, local first. Empty groups are left out. */
export function groupByLocation(models: ModelSpec[]): LocationGroup[] {
  return GROUPS.map((group) => ({
    ...group,
    models: models.filter((model) => model.location === group.location),
  })).filter((group) => group.models.length > 0);
}

export type ChatMode = "text" | "vision";

/**
 * Real chat models whose weights are on a backend, from every backend. Local models come
 * first, so the default is never the paid cloud endpoint; then loaded ones, then by id.
 */
export function usableModels(models: ModelSpec[], mode: ChatMode): ModelSpec[] {
  return models
    .filter(
      (model) =>
        !model.simulated &&
        model.downloaded === true &&
        model.tasks.includes("chat") &&
        (mode === "text" || model.modalities.includes("vision")),
    )
    .sort(
      (a, b) =>
        Number(a.location === "cloud") - Number(b.location === "cloud") ||
        Number(isRunning(b)) - Number(isRunning(a)) ||
        a.id.localeCompare(b.id),
    );
}

const DEFAULT_IMAGE_LIMIT = 1;
const AMD_CLOUD_IMAGE_LIMIT = 4;

/** Lemonade refuses more than one image in a message; the AMD cloud endpoint takes up to four. */
export function imageLimit(model: Pick<ModelSpec, "backend"> | undefined): number {
  return model?.backend === "amd_cloud" ? AMD_CLOUD_IMAGE_LIMIT : DEFAULT_IMAGE_LIMIT;
}

export interface MetricsSource {
  /** Who reports token counts and timings for a response. */
  reporter: string;
  /** Why per-response timings are missing, when the backend never reports them. */
  timingsReason: string | null;
}

export function metricsSource(
  model: Pick<ModelSpec, "backend" | "provider"> | undefined,
): MetricsSource {
  if (model?.backend === "amd_cloud" || model?.provider === "vllm") {
    return {
      reporter: "vLLM",
      timingsReason: "vLLM reports token counts but no per-response timings",
    };
  }
  const lemonade = !model || model.backend === "lemonade";
  return { reporter: lemonade ? "Lemonade" : "the backend", timingsReason: null };
}
