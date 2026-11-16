import { useQuery } from "@tanstack/react-query";

import type {
  BackendStatus,
  Capabilities,
  ExperimentRecord,
  HardwareProfile,
  Health,
  ModelInventory,
  SettingsView,
} from "./types";

const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {}

export async function fetchJson<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("Can't reach the Antar API. Start it with `uv run antar serve`.");
  }
  if (!response.ok) {
    throw new ApiError(`The Antar API returned ${response.status} for ${path}.`);
  }
  return (await response.json()) as T;
}

const STATUS_REFRESH_MS = 15_000;

export const useHealth = () =>
  useQuery({
    queryKey: ["health"],
    queryFn: () => fetchJson<Health>("/health"),
    refetchInterval: STATUS_REFRESH_MS,
  });

export const useBackends = () =>
  useQuery({
    queryKey: ["backends"],
    queryFn: async () => (await fetchJson<{ backends: BackendStatus[] }>("/api/v1/backends")).backends,
    refetchInterval: STATUS_REFRESH_MS,
  });

export const useSystem = () =>
  useQuery({ queryKey: ["system"], queryFn: () => fetchJson<HardwareProfile>("/api/v1/system") });

export const useModels = () =>
  useQuery({ queryKey: ["models"], queryFn: () => fetchJson<ModelInventory>("/api/v1/models") });

export const useCapabilities = () =>
  useQuery({
    queryKey: ["capabilities"],
    queryFn: () => fetchJson<Capabilities>("/api/v1/capabilities"),
  });

export const useSettings = () =>
  useQuery({ queryKey: ["settings"], queryFn: () => fetchJson<SettingsView>("/api/v1/settings") });

export const useExperiments = () =>
  useQuery({
    queryKey: ["experiments"],
    queryFn: async () =>
      (await fetchJson<{ experiments: ExperimentRecord[] }>("/api/v1/experiments")).experiments,
  });
