# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/) once it has a stable interface.

## [Unreleased]

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

- Quality evaluators, optimization executors, remote execution, deployment routing, and
  the speech, image-generation, and video modalities. See `docs/ROADMAP.md`.
