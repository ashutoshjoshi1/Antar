/** Mirrors the Antar API response models (apps/api/antar_api/schemas.py and antar/). */

export type Modality = "text" | "vision" | "speech" | "image" | "video";
export const MODALITIES: readonly Modality[] = ["text", "vision", "speech", "image", "video"];

export type Availability = "available" | "unavailable" | "not_configured" | "not_implemented";
export type BackendKind = "local" | "cloud" | "mock";
export type SupportLevel = "supported" | "documented" | "planned" | "unsupported";

export interface Health {
  status: "ok";
  version: string;
  time: string;
}

export interface BackendStatus {
  name: string;
  display_name: string;
  kind: BackendKind;
  availability: Availability;
  detail: string;
  endpoint: string | null;
  version: string | null;
  checked_at: string;
}

export interface Accelerator {
  name: string;
  kind: string;
  vendor: string | null;
  memory_bytes: number | null;
  shares_system_memory: boolean;
  cores: number | null;
}

export interface RuntimeSupport {
  name: string;
  available: boolean;
  version: string | null;
  detail: string;
}

export interface HardwareProfile {
  hostname: string;
  os: string;
  os_version: string;
  architecture: string;
  python_version: string;
  cpu_model: string;
  cpu_physical_cores: number | null;
  cpu_logical_cores: number | null;
  memory_total_bytes: number;
  memory_available_bytes: number;
  disk_total_bytes: number;
  disk_free_bytes: number;
  accelerators: Accelerator[];
  runtimes: RuntimeSupport[];
}

export interface ModelSpec {
  id: string;
  name: string;
  backend: string;
  modalities: Modality[];
  tasks: string[];
  revision: string | null;
  checkpoint: string | null;
  runtime: string | null;
  size_bytes: number | null;
  license: string | null;
  downloaded: boolean | null;
  loaded: boolean | null;
  quantization: string | null;
  context_length: number | null;
  labels: string[];
  simulated: boolean;
}

export interface InventorySource {
  backend: string;
  display_name: string;
  availability: Availability;
  model_count: number;
  detail: string;
}

export interface ModelInventory {
  models: ModelSpec[];
  sources: InventorySource[];
}

export interface MetricSpec {
  key: string;
  name: string;
  kind: "quality" | "performance";
  higher_is_better: boolean;
  unit: string | null;
  applies_to: string[];
}

export interface ModalityInfo {
  modality: Modality;
  description: string;
  tasks: string[];
  metrics: MetricSpec[];
}

export type Applicability = "candidate" | "limited" | "not_applicable";

export interface TechniqueApplicability {
  technique: string;
  modality: Modality;
  applicability: Applicability;
  note: string;
  implemented: boolean;
}

export interface Capability {
  modality: Modality;
  task: string | null;
  support: SupportLevel;
  note: string | null;
}

export interface BackendCapabilities {
  backend: string;
  display_name: string;
  kind: BackendKind;
  availability: Availability;
  capabilities: Capability[];
}

export interface Capabilities {
  modalities: ModalityInfo[];
  techniques: TechniqueApplicability[];
  backends: BackendCapabilities[];
}

export interface SettingsView {
  config_file: string;
  config_file_found: boolean;
  mock_backend_enabled: boolean;
  lemonade: { base_url: string; api_key_configured: boolean; timeout_seconds: number };
  amd_cloud: {
    name: string;
    ssh_host: string;
    ssh_user: string;
    ssh_port: number;
    ssh_key_configured: boolean;
    remote_workdir: string;
    rocm_version: string | null;
    gpus: { name: string; count: number; vram_gb: number | null }[];
  } | null;
  inference: { max_image_bytes: number; generation_timeout_seconds: number };
  storage: Record<
    "models_dir" | "artifacts_dir" | "training_dir" | "benchmarks_dir" | "experiments_dir",
    string
  >;
}

export interface MetricValue {
  key: string;
  value: number;
  unit: string | null;
}

export interface EvaluationResult {
  modality: Modality;
  task: string;
  methodology: string;
  metrics: MetricValue[];
  simulated: boolean;
}

export interface ExperimentRecord {
  id: string;
  name: string;
  model: { id: string; revision: string | null };
  backend: string;
  baseline: EvaluationResult | null;
  optimized: EvaluationResult | null;
  started_at: string;
  finished_at: string | null;
}

export type ImageMediaType = "image/png" | "image/jpeg" | "image/webp";

export interface ImageInput {
  media_type: ImageMediaType;
  data_base64: string;
}

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
  images?: ImageInput[];
}

export interface GenerationSettings {
  max_tokens: number;
  temperature?: number;
  top_p?: number;
  seed?: number;
  enable_thinking?: boolean;
}

export interface ChatBody {
  backend: string;
  model: string;
  messages: ChatMessage[];
  settings: GenerationSettings;
}

/** Null always means "not available", never zero. */
export interface InferenceMetrics {
  latency_ms: number;
  first_chunk_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cached_prompt_tokens: number | null;
  prompt_processing_ms: number | null;
  generation_ms: number | null;
  tokens_per_second: number | null;
}

export interface ChatResult {
  backend: string;
  model: string;
  content: string;
  reasoning: string | null;
  finish_reason: string | null;
  metrics: InferenceMetrics;
  simulated: boolean;
}

export type ChatStreamEvent =
  | { type: "delta"; content: string; reasoning: string }
  | { type: "done"; result: ChatResult }
  | { type: "error"; message: string; kind: string };

export interface DownloadJob {
  model: string;
  status: string;
  percent: number | null;
  bytes_downloaded: number | null;
  bytes_total: number | null;
  complete: boolean;
}

export interface Unavailable {
  metric: string;
  reason: string;
}

export interface Telemetry {
  system: {
    cpu_percent: number;
    memory_total_bytes: number;
    memory_available_bytes: number;
    processes: { label: string; pid: number; rss_bytes: number }[];
    unavailable: Unavailable[];
  };
  loaded_models: { backend: string; model: string }[];
  lemonade_stats: {
    time_to_first_token: number | null;
    tokens_per_second: number | null;
    request_count_total: number | null;
    output_tokens_total: number | null;
    live: { active_requests: number | null } | null;
  } | null;
  benchmark_running: boolean;
}

export interface Workload {
  id: string;
  name: string;
  description: string;
  modality: Modality;
  version: string;
  prompts: { id: string; text: string; image: string | null }[];
  check: "json" | null;
}

export type LoadPolicy = "keep" | "reload";

export interface BenchmarkConfig {
  name: string;
  model: { id: string };
  backend: string;
  workloads: string[];
  warmup_runs: number;
  measured_runs: number;
  max_tokens: number;
  temperature: number;
  seed: number | null;
  enable_thinking: boolean | null;
  load_policy: LoadPolicy;
}

export interface BenchmarkProgress {
  id: string;
  name: string;
  model: string;
  status: "running" | "completed" | "cancelled" | "failed";
  completed_requests: number;
  total_requests: number;
  current: string | null;
  started_at: string;
  failure: string | null;
}

export interface Aggregate {
  workload: string;
  completed: number;
  failed: number;
  error_rate: number;
  latency_ms_mean: number | null;
  latency_ms_median: number | null;
  latency_ms_p95: number | null;
  tokens_per_second_mean: number | null;
  tokens_per_second_median: number | null;
  first_chunk_ms_median: number | null;
  output_tokens_mean: number | null;
  json_valid_rate: number | null;
}

export interface RunRecord {
  index: number;
  workload: string;
  prompt_id: string;
  phase: "cold" | "warmup" | "measured";
  ok: boolean;
  error: string | null;
  metrics: InferenceMetrics | null;
  response: string | null;
  finish_reason: string | null;
  json_valid: boolean | null;
  manual_score: number | null;
  manual_notes: string | null;
}

export interface ReportSummary {
  id: string;
  name: string;
  status: "completed" | "cancelled" | "failed";
  simulated: boolean;
  model: string;
  quantization: string | null;
  backend: string;
  workloads: string[];
  overall: Aggregate | null;
  started_at: string;
  finished_at: string;
}

export interface BenchmarkReport {
  id: string;
  status: "completed" | "cancelled" | "failed";
  simulated: boolean;
  notes: string | null;
  antar_version: string;
  git_commit: string | null;
  backend: string;
  backend_version: string | null;
  model: {
    id: string;
    checkpoint: string | null;
    quantization: string | null;
    runtime: string | null;
    size_bytes: number | null;
  };
  hardware: HardwareProfile;
  config: BenchmarkConfig;
  workloads: Workload[];
  cold_start: { load_time_ms: number; first_request: RunRecord | null } | null;
  runs: RunRecord[];
  aggregates: Aggregate[];
  missing_telemetry: Unavailable[];
  failure: string | null;
  started_at: string;
  finished_at: string;
}
