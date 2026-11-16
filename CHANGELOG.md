# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow
[Semantic Versioning](https://semver.org/) once it has a stable interface.

## [Unreleased]

### Added

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

- Inference through real backends, optimization executors, the benchmark runner,
  evaluators, remote execution, and deployment routing. See `docs/ROADMAP.md`.
