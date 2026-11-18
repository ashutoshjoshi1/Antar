# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/) once it has a stable interface.

## [Unreleased]

### Added (Phase 2: AMD cloud inference and comparison)

Implemented with mocked tests. **Not yet run on real AMD hardware**; see
`docs/phase2-amd-cloud.md`.

- `amd_cloud` backend for a self-hosted vLLM OpenAI-compatible server: status, model
  discovery, text and image-understanding chat, streaming, cancellation, timeouts, and
  authentication and out-of-memory errors.
- Cloud endpoint settings with an allowlist: loopback, or an explicitly trusted HTTPS host
  with an API key.
- Operator scripts in `scripts/cloud/`: host preflight, explicit model download, start,
  check, and stop vLLM in Docker, GPU metrics, and an SSH tunnel.
- Read-only preflight and device-level `amd-smi` GPU readings over SSH, with a minimum
  polling interval.
- Memory feasibility estimate from a catalog of verified model facts.
- `ModelSpec` gains `location`, `provider`, `state`, `family`, and `parameter_count`.
- Reference-answer scoring (exact, number, keywords, JSON fields, opt-in unit tests) and
  six scored workloads, with two new synthetic images for diagrams and text in images.
- Comparison Lab: local versus cloud runs with per-row scope and measured-by labels, GPU
  usage, transport round trip, cloud usage estimate, time budget, cancellation, and JSON,
  CSV, and Markdown export.
- Operator-entered cloud cost session and estimate; confirmation required before a
  comparison uses cloud time.
- Optional registration of the endpoint with Lemonade's experimental cloud routing; models
  Lemonade relays to a cloud provider are marked as running in the cloud.
- CLI: `antar cloud-status`, `antar cloud-preflight`, `antar cloud-estimate`.
- Opt-in live tests against a real endpoint (`pytest -m amd_live`). Not yet executed.
- Dashboard: AMD Cloud, Comparison Lab, and Experiment History pages; location filters and
  cloud models in Models, Playground, and Vision; cloud settings.

### Changed (Phase 2)

- The AMD cloud backend now connects to the configured endpoint. It previously reported
  `not_implemented` and never opened a connection.
- `AmdCloudProfile.ssh_user` is optional, so an SSH config alias can supply it.
- A chat message may carry up to four images. Lemonade still accepts one per message and
  its adapter refuses more.
- Benchmarks and comparisons share one job slot; the "busy" message names both.
- Benchmark reports record where the model ran, a remote GPU sample for cloud runs, and
  automatic scores.
- OpenAI wire-format helpers moved to `antar/inference/openai.py`.

### Added (Phase 1: local inference)

- Lemonade chat adapter: text and image-understanding chat, streaming over Server-Sent
  Events, cancellation that stops generation in Lemonade, separate reasoning output.
- Model load, unload, and explicitly confirmed download. Antar refuses to load or run a
  model that is not downloaded, because Lemonade would otherwise download it implicitly.
- Per-request metrics built from the backend's per-response timings.
- Benchmark runner with general QA, code generation, structured JSON, and basic vision
  workloads; cold and warm runs kept apart; mean, median, and P95 latency; tokens per
  second; error rate; saved reports with JSON and CSV export and manual review fields.
- Live telemetry endpoint that labels unavailable measurements with the reason.
- Dashboard: Playground, Vision, Benchmarks lab, model actions, and a live System page.
- Opt-in live tests against a real Lemonade server (`pytest -m lemonade_live`).

### Changed

- `RuntimeBackend.generate_text` is replaced by `chat` and `chat_stream`.
- `BenchmarkConfig` now describes a runnable benchmark (workloads, runs, load policy).
- The Lemonade backend reports text chat and image understanding as `supported`.

### Added (Phase 0: foundation)

- Repository foundation: Python library, FastAPI app, Typer CLI, React dashboard.
- Typed specifications for models, hardware, backends, optimization jobs, benchmarks,
  evaluation results, experiment records, and deployment manifests.
- Local hardware detection (CPU, memory, disk; GPU enumeration on macOS).
- Lemonade adapter: connectivity check and model discovery against the documented `/v1` API.
- AMD cloud profile validation (no remote execution).
- Mock backend producing deterministic, clearly simulated text output.
- API endpoints: `/health`, `/api/v1/system`, `/backends`, `/models`, `/capabilities`,
  `/settings`, `/experiments`.
- Dashboard pages: Overview, Models, Hardware, Optimization, Benchmarks, Deployments,
  Settings.
- CI for linting, type checking, tests, and the dashboard build.

### Not yet implemented

- Optimization executors, remote training, deployment routing, quality evaluation on
  external datasets, and the speech, image-generation, and video modalities. See
  `docs/ROADMAP.md`.
