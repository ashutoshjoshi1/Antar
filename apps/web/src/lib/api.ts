import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  BackendStatus,
  BenchmarkConfig,
  BenchmarkProgress,
  BenchmarkReport,
  Capabilities,
  DownloadJob,
  ExperimentRecord,
  HardwareProfile,
  Health,
  ModelInventory,
  ModelSpec,
  ReportSummary,
  SettingsView,
  Telemetry,
  Workload,
} from "./types";

export const API_BASE: string = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {}

const UNREACHABLE = "Can't reach the Antar API. Start it with `uv run antar serve`.";

/** The API's own explanation when it gives one, otherwise the HTTP status. */
export async function errorFrom(response: Response, path: string): Promise<ApiError> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const { detail } = body;
      if (typeof detail === "string") return new ApiError(detail);
      if (Array.isArray(detail)) {
        const first: unknown = detail[0];
        if (first && typeof first === "object" && "msg" in first && typeof first.msg === "string") {
          return new ApiError(`The request was not valid: ${first.msg}`);
        }
      }
    }
  } catch {
    // Not JSON; fall through to the status line.
  }
  return new ApiError(`The Antar API returned ${response.status} for ${path}.`);
}

export async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError(UNREACHABLE);
  }
  if (!response.ok) throw await errorFrom(response, path);
  return response;
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path, { headers: { Accept: "application/json" } });
  return (await response.json()) as T;
}

export async function sendJson<T>(path: string, body: unknown, method = "POST"): Promise<T> {
  const response = await request(path, {
    method,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
  });
  return (await response.json()) as T;
}

const STATUS_REFRESH_MS = 15_000;
const TELEMETRY_REFRESH_MS = 3_000;
const PROGRESS_REFRESH_MS = 1_000;
const DOWNLOAD_REFRESH_MS = 2_000;

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

export const useTelemetry = () =>
  useQuery({
    queryKey: ["telemetry"],
    queryFn: () => fetchJson<Telemetry>("/api/v1/telemetry"),
    refetchInterval: TELEMETRY_REFRESH_MS,
  });

export const useDownloads = () =>
  useQuery({
    queryKey: ["downloads"],
    queryFn: async () =>
      (await fetchJson<{ downloads: DownloadJob[] }>("/api/v1/models/downloads")).downloads,
    // Poll only while something is actually downloading.
    refetchInterval: (query) =>
      query.state.data?.some((job) => !job.complete) ? DOWNLOAD_REFRESH_MS : false,
  });

type ModelAction = "load" | "unload" | "download";

export function useModelAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ action, model }: { action: ModelAction; model: ModelSpec }) =>
      sendJson<unknown>(`/api/v1/models/${action}`, {
        backend: model.backend,
        model: model.id,
        ...(action === "download" && { confirm: true }),
      }),
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ["models"] }),
        client.invalidateQueries({ queryKey: ["downloads"] }),
        client.invalidateQueries({ queryKey: ["telemetry"] }),
      ]),
  });
}

export const useWorkloads = () =>
  useQuery({
    queryKey: ["workloads"],
    queryFn: async () =>
      (await fetchJson<{ workloads: Workload[] }>("/api/v1/benchmarks/workloads")).workloads,
    staleTime: Infinity,
  });

export const useBenchmarkHistory = () =>
  useQuery({
    queryKey: ["benchmarks"],
    queryFn: async () =>
      (await fetchJson<{ benchmarks: ReportSummary[] }>("/api/v1/benchmarks")).benchmarks,
  });

export const useBenchmarkReport = (id: string | null) =>
  useQuery({
    queryKey: ["benchmark", id],
    queryFn: () => fetchJson<BenchmarkReport>(`/api/v1/benchmarks/${id}`),
    enabled: id !== null,
  });

interface ActiveBenchmark {
  active: BenchmarkProgress | null;
}

export const useActiveBenchmark = () =>
  useQuery({
    queryKey: ["benchmark-active"],
    queryFn: async () => (await fetchJson<ActiveBenchmark>("/api/v1/benchmarks/active")).active,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? PROGRESS_REFRESH_MS : false,
  });

export function useStartBenchmark() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (config: BenchmarkConfig) => sendJson<ActiveBenchmark>("/api/v1/benchmarks", config),
    onSuccess: (data) => client.setQueryData(["benchmark-active"], data.active),
  });
}

export function useCancelBenchmark() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => sendJson<ActiveBenchmark>("/api/v1/benchmarks/active/cancel", {}),
    onSuccess: (data) => client.setQueryData(["benchmark-active"], data.active),
  });
}

interface Evaluation {
  reportId: string;
  runIndex: number;
  score: number | null;
  notes: string | null;
}

export function useEvaluateRun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, runIndex, score, notes }: Evaluation) =>
      sendJson<BenchmarkReport>(
        `/api/v1/benchmarks/${reportId}/runs/${runIndex}`,
        { score, notes },
        "PATCH",
      ),
    onSuccess: (report) => client.setQueryData(["benchmark", report.id], report),
  });
}
