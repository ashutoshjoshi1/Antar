import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  BackendStatus,
  BenchmarkConfig,
  BenchmarkProgress,
  BenchmarkReport,
  Capabilities,
  CloudSession,
  CloudStatus,
  ComparisonConfig,
  ComparisonProgress,
  ComparisonReport,
  ComparisonSummary,
  CostEstimate,
  DownloadJob,
  ExperimentRecord,
  FeasibilityBody,
  FeasibilityEstimate,
  GpuTelemetry,
  HardwareProfile,
  Health,
  KnownModel,
  LemonadeProviderStatus,
  ModelInventory,
  ModelSpec,
  PreflightReport,
  ReportSummary,
  SettingsView,
  Telemetry,
  Workload,
} from "./types";
import { gpuPollMs } from "./cloud";

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

const CLOUD = "/api/v1/cloud";
const COST_REFRESH_MS = 30_000;

export const useCloudStatus = () =>
  useQuery({
    queryKey: ["cloud-status"],
    queryFn: () => fetchJson<CloudStatus>(`${CLOUD}/status`),
    // Re-checked while the page is open, so a dropped tunnel or a finished model load shows up.
    refetchInterval: STATUS_REFRESH_MS,
  });

/** Polls no faster than the server samples, and only while a component using it is mounted. */
export const useCloudGpus = () =>
  useQuery({
    queryKey: ["cloud-gpus"],
    queryFn: () => fetchJson<GpuTelemetry>(`${CLOUD}/gpus`),
    refetchInterval: (query) => gpuPollMs(query.state.data),
  });

/** A slow, read-only SSH check. Runs only when the user asks for it. */
export const usePreflight = () =>
  useMutation({ mutationFn: () => sendJson<PreflightReport>(`${CLOUD}/preflight`, undefined) });

export const useCloudCatalog = () =>
  useQuery({
    queryKey: ["cloud-catalog"],
    queryFn: async () => (await fetchJson<{ models: KnownModel[] }>(`${CLOUD}/catalog`)).models,
    staleTime: Infinity,
  });

export const useFeasibility = () =>
  useMutation({
    mutationFn: (body: FeasibilityBody) =>
      sendJson<FeasibilityEstimate>(`${CLOUD}/feasibility`, body),
  });

export const useCloudCost = () =>
  useQuery({
    queryKey: ["cloud-cost"],
    queryFn: () => fetchJson<CostEstimate>(`${CLOUD}/cost`),
    // The server recomputes spend and warnings from its own clock.
    refetchInterval: (query) => (query.state.data?.running ? COST_REFRESH_MS : false),
  });

export function useSetCloudCost() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (session: CloudSession) => sendJson<CostEstimate>(`${CLOUD}/cost`, session, "PUT"),
    onSuccess: (estimate) => client.setQueryData(["cloud-cost"], estimate),
  });
}

export const useLemonadeProvider = () =>
  useQuery({
    queryKey: ["lemonade-provider"],
    queryFn: () => fetchJson<LemonadeProviderStatus>(`${CLOUD}/lemonade-provider`),
  });

/** Registers or removes Antar's endpoint in Lemonade's cloud routing. Registering needs confirmation. */
export function useLemonadeProviderAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (action: "register" | "remove") =>
      action === "register"
        ? sendJson<LemonadeProviderStatus>(`${CLOUD}/lemonade-provider`, { confirm: true })
        : sendJson<LemonadeProviderStatus>(`${CLOUD}/lemonade-provider`, undefined, "DELETE"),
    onSuccess: (status) => {
      client.setQueryData(["lemonade-provider"], status);
      // Lemonade lists a registered provider's models as its own.
      void client.invalidateQueries({ queryKey: ["models"] });
    },
  });
}

const COMPARISONS = "/api/v1/comparisons";

interface ActiveComparison {
  active: ComparisonProgress | null;
}

export const useComparisonHistory = () =>
  useQuery({
    queryKey: ["comparisons"],
    queryFn: async () =>
      (await fetchJson<{ comparisons: ComparisonSummary[] }>(COMPARISONS)).comparisons,
  });

export const useComparison = (id: string | null) =>
  useQuery({
    queryKey: ["comparison", id],
    queryFn: () => fetchJson<ComparisonReport>(`${COMPARISONS}/${id}`),
    enabled: id !== null,
  });

export const useActiveComparison = () =>
  useQuery({
    queryKey: ["comparison-active"],
    queryFn: async () => (await fetchJson<ActiveComparison>(`${COMPARISONS}/active`)).active,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? PROGRESS_REFRESH_MS : false,
  });

/** Starting keeps a paid instance busy, so the caller must have confirmed it. */
export function useStartComparison() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (config: ComparisonConfig) =>
      sendJson<ActiveComparison>(COMPARISONS, { config, confirm_cloud_usage: true }),
    onSuccess: (data) => client.setQueryData(["comparison-active"], data.active),
  });
}

export function useCancelComparison() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => sendJson<ActiveComparison>(`${COMPARISONS}/active/cancel`, {}),
    onSuccess: (data) => client.setQueryData(["comparison-active"], data.active),
  });
}

export type ExportFormat = "json" | "csv" | "md";

export const comparisonExportUrl = (id: string, format: ExportFormat): string =>
  `${API_BASE}${COMPARISONS}/${id}/export?format=${format}`;
