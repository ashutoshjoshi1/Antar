/** Mirrors the Antar API response models (apps/api/antar_api/schemas.py and antar/). */

export type Modality = "text" | "vision" | "speech" | "image" | "video";
export const MODALITIES: readonly Modality[] = ["text", "vision", "speech", "image", "video"];

export type Availability = "available" | "unavailable" | "not_configured" | "not_implemented";
export type BackendKind = "local" | "cloud" | "mock";
export type ExecutionLocation = "local" | "cloud" | "mock";
export type ModelState = "configured" | "discovered" | "installed" | "loaded";
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
  /** Where inference runs. Null when the backend did not say. */
  location: ExecutionLocation | null;
  provider: string | null;
  state: ModelState | null;
  family: string | null;
  /** From published metadata, never estimated. */
  parameter_count: number | null;
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
    ssh_user: string | null;
    ssh_port: number;
    ssh_key_configured: boolean;
    remote_workdir: string;
    rocm_version: string | null;
    gpus: { name: string; count: number; vram_gb: number | null }[];
  } | null;
  /** The configured cloud endpoint. The API key is only ever a boolean. */
  cloud: {
    base_url: string;
    loopback: boolean;
    api_key_configured: boolean;
    trusted_hosts: string[];
    declared_models: string[];
    vllm_image: string | null;
    generation_timeout_seconds: number;
  } | null;
  cloud_cost: {
    hourly_price_usd: number | null;
    credit_balance_usd: number | null;
    max_experiment_minutes: number;
  };
  inference: { max_image_bytes: number; generation_timeout_seconds: number };
  storage: Record<
    | "models_dir"
    | "artifacts_dir"
    | "training_dir"
    | "benchmarks_dir"
    | "experiments_dir"
    | "comparisons_dir",
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

export type ScoreMethod = "exact" | "number" | "keywords" | "json_fields" | "python_tests";

/** The reference for one prompt and the rule a response is compared with. */
export interface Expectation {
  method: ScoreMethod;
  answer: string | null;
  number: number | null;
  keywords: string[];
  fields: Record<string, string>;
  values: Record<string, unknown>;
  tests: string[];
}

export interface BenchmarkPrompt {
  id: string;
  text: string;
  image: string | null;
  /** Null: reviewed by a person, not scored. */
  expect: Expectation | null;
}

export interface Workload {
  id: string;
  name: string;
  description: string;
  modality: Modality;
  version: string;
  prompts: BenchmarkPrompt[];
  check: "json" | null;
  license: string | null;
  provenance: string | null;
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
  allow_code_execution: boolean;
  /** Required, and only ever sent, when the model runs in the cloud: the run uses paid instance time. */
  confirm_cloud_usage?: boolean;
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
  /** Measured responses that were auto-scored. */
  scored: number;
  /** Mean automatic score over the scored responses, 0 to 1. */
  accuracy: number | null;
  decode_tokens_per_second_median: number | null;
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
  /** 0 to 1. Set only for prompts that have a reference answer. */
  score: number | null;
  score_method: string | null;
  score_detail: string | null;
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
    revision: string | null;
    parameter_count: number | null;
    context_length: number | null;
  };
  hardware: HardwareProfile;
  /** Where the model ran. Null in reports from before this field. */
  execution: ExecutionLocation | null;
  /** GPUs of the remote host at the start of a cloud run. */
  remote_gpus: GpuSample | null;
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

export interface GpuReading {
  index: number;
  name: string | null;
  memory_total_bytes: number | null;
  memory_used_bytes: number | null;
  utilization_percent: number | null;
  temperature_celsius: number | null;
  power_watts: number | null;
}

/** Device-level readings: a whole GPU, not a model or a request. */
export interface GpuSample {
  collected_at: string;
  gpus: GpuReading[];
  driver_version: string | null;
  rocm_version: string | null;
  amd_smi_version: string | null;
  unavailable: Unavailable[];
}

export interface CloudStatus {
  endpoint_configured: boolean;
  base_url: string | null;
  loopback: boolean | null;
  api_key_configured: boolean;
  ssh_configured: boolean;
  ssh_host: string | null;
  vllm_image: string | null;
  status: BackendStatus;
  /** One GET /health round trip, measured by the Antar API. */
  round_trip_ms: number | null;
  models: ModelSpec[];
}

export interface GpuTelemetry {
  ssh_configured: boolean;
  interval_seconds: number | null;
  sample: GpuSample | null;
  reason: string | null;
}

export type CheckStatus = "pass" | "warn" | "fail" | "skip";

export interface PreflightCheck {
  id: string;
  status: CheckStatus;
  detail: string;
  remediation: string | null;
}

export interface PreflightReport {
  checked_at: string;
  checks: PreflightCheck[];
  facts: Record<string, string>;
}

export interface KnownModel {
  id: string;
  name: string;
  family: string;
  modalities: Modality[];
  license: string;
  revision: string;
  parameter_count: number;
  weights_bytes: number;
  precision: string;
  context_length: number;
  num_layers: number;
  hidden_size: number;
  num_attention_heads: number;
  num_key_value_heads: number;
  reasoning_parser: string | null;
  note: string | null;
}

export interface FeasibilityBody {
  model: string;
  gpu_count: number;
  gpu_memory_bytes: number;
  max_model_len: number | null;
  concurrency: number;
}

export type Verdict = "fits" | "tight" | "does_not_fit";

/** Arithmetic on published model facts, not a measurement. */
export interface FeasibilityEstimate {
  model: string;
  gpu_count: number;
  max_model_len: number;
  concurrency: number;
  weights_bytes: number;
  kv_cache_bytes: number;
  kv_cache_bytes_per_token: number;
  runtime_overhead_bytes: number;
  required_bytes: number;
  usable_bytes: number;
  total_bytes: number;
  headroom_bytes: number;
  verdict: Verdict;
  max_concurrency_at_full_context: number;
  notes: string[];
}

/** The operator's own record of the paid instance. Antar verifies none of it. */
export interface CloudSession {
  hourly_price_usd: number | null;
  credit_balance_usd: number | null;
  instance_started_at: string | null;
  instance_stopped_at: string | null;
}

export interface CostEstimate extends CloudSession {
  running: boolean;
  elapsed_seconds: number | null;
  estimated_spend_usd: number | null;
  estimated_remaining_usd: number | null;
  estimated_hours_remaining: number | null;
  max_experiment_minutes: number;
  warnings: string[];
}

export interface LemonadeCloudProvider {
  name: string;
  base_url: string | null;
  env_var_set: boolean | null;
  runtime_key_set: boolean | null;
  models_discovered: number | null;
  allow_insecure_http: boolean | null;
  warnings: string[];
}

export interface LemonadeProviderStatus {
  name: string;
  lemonade_reachable: boolean;
  /** Null when Lemonade could not be asked. */
  supported: boolean | null;
  provider: LemonadeCloudProvider | null;
  detail: string | null;
}

export type Side = "local" | "cloud";

export interface ComparisonTarget {
  backend: string;
  model: { id: string; revision?: string | null };
}

export interface ComparisonConfig {
  name: string;
  local: ComparisonTarget;
  cloud: ComparisonTarget;
  workloads: string[];
  warmup_runs: number;
  measured_runs: number;
  max_tokens: number;
  temperature: number;
  seed: number | null;
  enable_thinking: boolean | null;
  allow_code_execution: boolean;
  /** Null: the configured experiment limit. */
  time_budget_minutes: number | null;
}

export interface ComparisonProgress {
  id: string;
  name: string;
  status: "running" | "completed" | "cancelled" | "failed";
  side: Side | null;
  completed_requests: number;
  total_requests: number;
  current: string | null;
  started_at: string;
  budget_seconds: number;
  failure: string | null;
}

export type MeasuredBy = "antar" | "backend" | "scorer";
export type Scope = "end_to_end" | "model" | "quality" | "reliability";

export interface ComparisonRow {
  /** A workload id, or "all". */
  workload: string;
  metric: string;
  label: string;
  unit: string | null;
  scope: Scope;
  measured_by: MeasuredBy;
  /** Null: not available. Never zero. */
  local: number | null;
  cloud: number | null;
}

export interface TransportMeasurement {
  samples_ms: number[];
  median_ms: number | null;
  note: string;
}

export interface GpuUsageSummary {
  samples: number;
  interval_seconds: number | null;
  gpu_count: number | null;
  gpu_names: string[];
  memory_total_bytes: number | null;
  memory_used_peak_bytes: number | null;
  utilization_mean_percent: number | null;
  utilization_peak_percent: number | null;
  power_peak_watts: number | null;
  driver_version: string | null;
  rocm_version: string | null;
  unavailable: Unavailable[];
}

export interface CloudUsage {
  cloud_seconds: number | null;
  hourly_price_usd: number | null;
  estimated_cost_usd: number | null;
  note: string;
}

export interface ComparisonReport {
  id: string;
  status: "completed" | "cancelled" | "failed";
  /** True if either side was a mock backend. */
  simulated: boolean;
  antar_version: string;
  git_commit: string | null;
  config: ComparisonConfig;
  local: BenchmarkReport | null;
  cloud: BenchmarkReport | null;
  rows: ComparisonRow[];
  transport: TransportMeasurement | null;
  gpu: GpuUsageSummary | null;
  usage: CloudUsage;
  /** Container image as declared in the configuration, not probed. */
  vllm_image: string | null;
  lemonade_version: string | null;
  caveats: string[];
  failure: string | null;
  started_at: string;
  finished_at: string;
}

export interface ComparisonSummary {
  id: string;
  name: string;
  status: "completed" | "cancelled" | "failed";
  simulated: boolean;
  local_model: string;
  local_backend: string;
  cloud_model: string;
  cloud_backend: string;
  workloads: string[];
  git_commit: string | null;
  estimated_cost_usd: number | null;
  started_at: string;
  finished_at: string;
}
