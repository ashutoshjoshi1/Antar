import type {
  Aggregate,
  BenchmarkReport,
  CloudStatus,
  ComparisonReport,
  ComparisonRow,
  CostEstimate,
  HardwareProfile,
  ModelSpec,
  RunRecord,
  SettingsView,
  Workload,
} from "../lib/types";

/** A downloaded, loaded local Lemonade chat model unless overridden. */
export function model(overrides: Partial<ModelSpec> = {}): ModelSpec {
  return {
    id: "Qwen3-1.7B-GGUF",
    name: "Qwen3-1.7B-GGUF",
    backend: "lemonade",
    modalities: ["text"],
    tasks: ["chat"],
    revision: null,
    checkpoint: "unsloth/Qwen3-1.7B-GGUF:Q4_0",
    runtime: "llamacpp",
    size_bytes: 984_000_000,
    license: null,
    downloaded: true,
    loaded: true,
    quantization: "Q4_0",
    context_length: 40960,
    labels: ["chat", "reasoning"],
    simulated: false,
    location: "local",
    provider: "lemonade",
    state: "loaded",
    family: null,
    parameter_count: null,
    ...overrides,
  };
}

export const CLOUD_MODEL = model({
  id: "Qwen/Qwen3-32B",
  name: "Qwen3 32B",
  backend: "amd_cloud",
  modalities: ["text"],
  checkpoint: "Qwen/Qwen3-32B",
  runtime: "vllm",
  size_bytes: 65_524_328_560,
  license: "apache-2.0",
  revision: "9216db5781bf21249d130ec9da846c4624c16137",
  quantization: "BF16",
  context_length: 16384,
  labels: [],
  location: "cloud",
  provider: "vllm",
  state: "loaded",
  family: "Qwen3",
  parameter_count: 32_762_123_264,
});

export const MOCK_SMALL = model({
  id: "mock/echo-small",
  backend: "mock",
  checkpoint: null,
  runtime: "mock",
  size_bytes: null,
  quantization: null,
  context_length: null,
  simulated: true,
  location: "mock",
  provider: "mock",
});
export const MOCK_LARGE = { ...MOCK_SMALL, id: "mock/echo-large" };

const prompts = (prefix: string, count: number, scored: boolean, image: string | null = null) =>
  Array.from({ length: count }, (_, index) => ({
    id: `${prefix}${index + 1}`,
    text: `Question ${index + 1}?`,
    image,
    expect: scored
      ? { method: "exact" as const, answer: "Jupiter", number: null, keywords: [], fields: {}, values: {}, tests: [] }
      : null,
  }));

export function workload(overrides: Partial<Workload> & Pick<Workload, "id" | "name">): Workload {
  return {
    description: "Short questions.",
    modality: "text",
    version: "1",
    check: null,
    license: null,
    provenance: null,
    prompts: prompts("p", 4, false),
    ...overrides,
  };
}

export const WORKLOADS: Workload[] = [
  workload({ id: "general_qa", name: "General question answering" }),
  workload({ id: "vision_basic", name: "Basic image understanding", description: "Images.", modality: "vision", prompts: prompts("v", 3, false, "x.png") }),
  workload({ id: "qa_exact", name: "Factual questions (exact answers)", license: "CC0-1.0", prompts: prompts("q", 2, true) }),
  workload({ id: "code_tests", name: "Code generation (unit tested)", license: "CC0-1.0", prompts: prompts("c", 3, true) }),
];

export const HARDWARE: HardwareProfile = {
  hostname: "test-host",
  os: "Darwin",
  os_version: "27.0",
  architecture: "arm64",
  python_version: "3.13.0",
  cpu_model: "Test CPU",
  cpu_physical_cores: 8,
  cpu_logical_cores: 8,
  memory_total_bytes: 16_000_000_000,
  memory_available_bytes: 4_000_000_000,
  disk_total_bytes: 500_000_000_000,
  disk_free_bytes: 100_000_000_000,
  accelerators: [],
  runtimes: [],
};

export function aggregate(overrides: Partial<Aggregate> = {}): Aggregate {
  return {
    workload: "all",
    completed: 2,
    failed: 0,
    error_rate: 0,
    latency_ms_mean: null,
    latency_ms_median: null,
    latency_ms_p95: null,
    tokens_per_second_mean: null,
    tokens_per_second_median: null,
    first_chunk_ms_median: null,
    output_tokens_mean: null,
    json_valid_rate: null,
    scored: 0,
    accuracy: null,
    decode_tokens_per_second_median: null,
    ...overrides,
  };
}

export function run(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    index: 0,
    workload: "qa_exact",
    prompt_id: "q1",
    phase: "measured",
    ok: true,
    error: null,
    metrics: null,
    response: "Jupiter",
    finish_reason: "stop",
    json_valid: null,
    score: null,
    score_method: null,
    score_detail: null,
    manual_score: null,
    manual_notes: null,
    ...overrides,
  };
}

export function benchmarkReport(overrides: Partial<BenchmarkReport> = {}): BenchmarkReport {
  return {
    id: "bench-1",
    status: "completed",
    simulated: false,
    notes: null,
    antar_version: "0.1.0",
    git_commit: "c302fab",
    backend: "lemonade",
    backend_version: "2026.46.2",
    model: { id: "Qwen3-1.7B-GGUF", checkpoint: null, quantization: "Q4_0", runtime: "llamacpp", size_bytes: 984_000_000, revision: null, parameter_count: null, context_length: 40960 },
    hardware: HARDWARE,
    execution: "local",
    remote_gpus: null,
    config: {
      name: "run",
      model: { id: "Qwen3-1.7B-GGUF" },
      backend: "lemonade",
      workloads: ["qa_exact"],
      warmup_runs: 1,
      measured_runs: 1,
      max_tokens: 256,
      temperature: 0,
      seed: 42,
      enable_thinking: false,
      load_policy: "keep",
      allow_code_execution: false,
    },
    workloads: WORKLOADS.filter((item) => item.id === "qa_exact"),
    cold_start: null,
    runs: [],
    aggregates: [],
    missing_telemetry: [],
    failure: null,
    started_at: "2026-11-18T10:00:00Z",
    finished_at: "2026-11-18T10:01:00Z",
    ...overrides,
  };
}

export function row(overrides: Partial<ComparisonRow> & Pick<ComparisonRow, "metric" | "label">): ComparisonRow {
  return { workload: "all", unit: "ms", scope: "end_to_end", measured_by: "antar", local: null, cloud: null, ...overrides };
}

export function comparisonReport(overrides: Partial<ComparisonReport> = {}): ComparisonReport {
  return {
    id: "cmp-1",
    status: "completed",
    simulated: false,
    antar_version: "0.1.0",
    git_commit: "c302fab",
    config: {
      name: "Qwen3-1.7B-GGUF vs Qwen/Qwen3-32B",
      local: { backend: "lemonade", model: { id: "Qwen3-1.7B-GGUF" } },
      cloud: { backend: "amd_cloud", model: { id: "Qwen/Qwen3-32B" } },
      workloads: ["qa_exact"],
      warmup_runs: 1,
      measured_runs: 1,
      max_tokens: 256,
      temperature: 0,
      seed: 42,
      enable_thinking: false,
      allow_code_execution: false,
      time_budget_minutes: 30,
    },
    local: benchmarkReport({ id: "cmp-1-local" }),
    cloud: benchmarkReport({
      id: "cmp-1-cloud",
      backend: "amd_cloud",
      backend_version: "0.34.0",
      execution: "cloud",
      model: { id: "Qwen/Qwen3-32B", checkpoint: "Qwen/Qwen3-32B", quantization: "BF16", runtime: "vllm", size_bytes: 65_524_328_560, revision: "9216db5781bf", parameter_count: 32_762_123_264, context_length: 16384 },
    }),
    rows: [],
    transport: null,
    gpu: null,
    usage: { cloud_seconds: null, hourly_price_usd: null, estimated_cost_usd: null, note: "Estimated from this run's duration and the hourly price entered by the operator." },
    vllm_image: "vllm/vllm-openai-rocm:v0.34.0-rocm100",
    lemonade_version: "2026.46.2",
    caveats: [
      "Not a hardware-normalized comparison. The two sides differ in model size, weight precision, hardware, and network path at the same time.",
      "vLLM reports token counts but no per-response timings.",
    ],
    failure: null,
    started_at: "2026-11-18T10:00:00Z",
    finished_at: "2026-11-18T10:05:00Z",
    ...overrides,
  };
}

export function cloudStatus(overrides: Partial<CloudStatus> = {}): CloudStatus {
  return {
    endpoint_configured: false,
    base_url: null,
    loopback: null,
    api_key_configured: false,
    ssh_configured: false,
    ssh_host: null,
    vllm_image: null,
    status: {
      name: "amd_cloud",
      display_name: "AMD cloud (vLLM on ROCm)",
      kind: "cloud",
      availability: "not_configured",
      detail: "No cloud endpoint configured. Set ANTAR_CLOUD__BASE_URL to the tunnelled vLLM address.",
      endpoint: null,
      version: null,
      checked_at: "2026-11-18T10:00:00Z",
    },
    round_trip_ms: null,
    models: [],
    ...overrides,
  };
}

export const CLOUD_UP: CloudStatus = cloudStatus({
  endpoint_configured: true,
  base_url: "http://127.0.0.1:8000/v1",
  loopback: true,
  api_key_configured: true,
  ssh_configured: true,
  ssh_host: "amd-host",
  status: {
    name: "amd_cloud",
    display_name: "AMD cloud (vLLM on ROCm)",
    kind: "cloud",
    availability: "available",
    detail: "Connected. Serving: Qwen/Qwen3-32B.",
    endpoint: "http://127.0.0.1:8000/v1",
    version: "0.34.0",
    checked_at: "2026-11-18T10:00:00Z",
  },
  round_trip_ms: 41.6,
  models: [CLOUD_MODEL],
});

export function costEstimate(overrides: Partial<CostEstimate> = {}): CostEstimate {
  return {
    hourly_price_usd: null,
    credit_balance_usd: null,
    instance_started_at: null,
    instance_stopped_at: null,
    running: false,
    elapsed_seconds: null,
    estimated_spend_usd: null,
    estimated_remaining_usd: null,
    estimated_hours_remaining: null,
    max_experiment_minutes: 30,
    warnings: [],
    ...overrides,
  };
}

/** Settings as the API reports them with no cloud configured. */
export const SETTINGS: SettingsView = {
  config_file: "configs/antar.yaml",
  config_file_found: false,
  mock_backend_enabled: true,
  lemonade: { base_url: "http://localhost:13305/v1", api_key_configured: false, timeout_seconds: 3 },
  amd_cloud: null,
  cloud: null,
  cloud_cost: { hourly_price_usd: null, credit_balance_usd: null, max_experiment_minutes: 30 },
  inference: { max_image_bytes: 8 * 1024 * 1024, generation_timeout_seconds: 300 },
  storage: {
    models_dir: "data/models",
    artifacts_dir: "data/artifacts",
    training_dir: "data/training",
    benchmarks_dir: "data/benchmarks",
    experiments_dir: "data/experiments",
    comparisons_dir: "data/comparisons",
  },
};

/** Settings with a tunnelled cloud endpoint and an SSH host. */
export const CLOUD_SETTINGS: SettingsView = {
  ...SETTINGS,
  amd_cloud: {
    name: "lab",
    ssh_host: "amd-box",
    ssh_user: null,
    ssh_port: 22,
    ssh_key_configured: false,
    remote_workdir: "~/antar",
    rocm_version: null,
    gpus: [],
  },
  cloud: {
    base_url: "http://127.0.0.1:18000/v1",
    loopback: true,
    api_key_configured: true,
    trusted_hosts: [],
    declared_models: [],
    vllm_image: "vllm/vllm-openai-rocm:v0.34.0-rocm100",
    generation_timeout_seconds: 600,
  },
};
