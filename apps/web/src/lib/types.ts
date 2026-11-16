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
