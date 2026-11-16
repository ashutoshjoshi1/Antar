# CLAUDE.md — Antar

Antar (अन्तर) is an open-source platform for multimodal AI model optimization,
benchmarking, and cloud-to-edge deployment. Local target: AMD Lemonade. Cloud target: AMD
Instinct GPUs via ROCm. Primary development machine: an Apple Silicon Mac.

The repository is **pre-alpha**. Real local text and vision inference and performance
benchmarking work (Phase 1). Optimization, quality evaluation, cloud execution, and
deployment do not. Read `README.md` → "Current implementation status" before assuming
anything else works.

## Project rules

These are binding for every session.

1. **Never fabricate results.** No benchmark numbers, quality claims, or "improvements" that
   were not produced by a recorded experiment. Not in code, tests-as-fixtures-presented-as-data,
   docs, UI, or commit messages. Mock output is always flagged `simulated=True` and labelled
   "Simulated" in the UI.
2. **Never claim unsupported functionality.** Backends declare a `SupportLevel` per
   modality. `SUPPORTED` means Antar can execute it today. Unfinished UI is marked
   "Not built yet".
3. **Never commit secrets or model weights.** Credentials come from the environment or
   `.env`. `.gitignore` blocks `.env`, `configs/antar.yaml`, keys, and weight formats —
   do not weaken it. API responses expose secrets only as booleans.
4. **Verify external APIs before implementing against them.** Check current official docs
   (Lemonade, ROCm, PyTorch, Hugging Face) and record what you checked and when in the
   module docstring, as `antar/backends/lemonade/client.py` does. Do not rely on memory.
5. **Preserve compatibility with supported Lemonade APIs.** Use the documented `/v1`
   prefix. Do not reimplement what Lemonade already does (model management, engine
   selection, serving).
6. **Local development must work without AMD cloud access**, and without Lemonade running.
   An unreachable backend is a status, never a crash.
7. **Keep ROCm isolated from the macOS install.** GPU/ML dependencies live only in the
   `ml` extra. Never add torch, ROCm wheels, or CUDA packages to base dependencies, and
   never import torch at module import time in `antar/`.
8. **No silent cloud cost.** Do not add code paths that start, resize, or keep alive paid
   resources without an explicit user action. `AmdCloudBackend` must not open network
   connections until remote execution is deliberately implemented.
   **Never trigger a model download implicitly.** Lemonade's `/load` and
   `/chat/completions` download missing models on their own; every call path must go
   through `LemonadeBackend._require_downloaded` first. Downloads happen only through the
   explicit, confirmed download action.
9. **Do not push, open PRs, create remotes, or run paid cloud operations without the
   maintainer's explicit authorization** in the current session.
10. **Keep the architecture modular.** New engines implement `RuntimeBackend` and register
    in `antar/backends/registry.py`; nothing else should need restructuring.
11. **Typed Python and TypeScript.** `mypy --strict` and `tsc` strict must pass. No `Any`
    / `any` without a comment explaining why.
12. **Test meaningful functionality.** Behaviour, validation rules, and failure paths —
    not getters. Tests never touch the network; stub Lemonade with `httpx.MockTransport`.
13. **Prefer working vertical slices over speculative abstractions.** Do not add
    directories, base classes, or config for features that are not being built now.
14. **Update documentation when architecture or interfaces change** — at minimum
    `README.md` status, `docs/architecture/overview.md`, and `docs/ROADMAP.md`. If the API
    changes, update `apps/web/src/lib/types.ts` in the same change.

## Layout

```
antar/                 Python library (the product)
  core/                Modality/Task vocabulary, errors
  config/              Settings: env > .env > YAML
  hardware/            HardwareProfile + local detection
  models/              ModelSpec, inventory across backends
  modalities/          Catalog of tasks and metrics per modality
  backends/            RuntimeBackend interface; lemonade/, amd_cloud/, mock/
  inference/           Chat types, per-request metrics, image validation, service
  optimization/        OptimizationJob + technique applicability (no executors yet)
  benchmarking/        Workloads, runner, report + statistics, store, job manager
  evaluation/          EvaluationResult, DatasetRef
  orchestration/       ExperimentRecord + filesystem store
  deployment/          DeploymentManifest, RoutingPolicy
apps/api/antar_api/    FastAPI app (thin handlers over antar/)
apps/cli/antar_cli/    Typer CLI
apps/web/              React + TypeScript + Vite + Tailwind v4 dashboard
configs/               Example YAML for every typed spec (validated by tests)
tests/unit, tests/integration
docs/                  architecture, installation, developer-guide, benchmarks, challenge
```

Subpackages for individual modalities or techniques (`modalities/text/`,
`optimization/quantization/`, …) are created when their first real implementation lands,
not before.

## Commands

```bash
make install            # uv sync + pnpm install
make api                # API on :8080 with reload
make web                # dashboard on :5173 (proxies /api and /health to :8080)
make format             # ruff format + autofix
make check              # everything CI runs (API + web)

uv run pytest tests/unit/test_lemonade.py -k status   # a subset
uv run pytest -m lemonade_live                        # real Lemonade; needs a downloaded model
uv run mypy
cd apps/web && pnpm test && pnpm typecheck && pnpm lint
```

Install the ML stack only when working on training code: `uv sync --extra ml`.

## Conventions

- Pydantic models are frozen. Return new objects; do not mutate.
- Optional fields mean "the source did not say" — never fill them with estimates.
- All timestamps are timezone-aware UTC (`antar.core.types.utc_now`).
- `None` in a metric means "not available". Never substitute zero, and never compute a
  per-request number from Lemonade's server-wide `/v1/stats`.
- Label who measured a number (Lemonade, the Antar API, or the browser) wherever it is shown.
- Editing a benchmark workload's prompts requires bumping its `version`.
- The browser never calls Lemonade; requests name a configured backend, never a URL.
- API handlers stay thin; logic lives in `antar/` where the CLI can use it too.
- Frontend: server state via TanStack Query hooks in `src/lib/api.ts`; shareable UI state
  (filters) in the URL; design tokens in `src/styles/global.css`. Lemon = local,
  periwinkle = cloud; do not use those two colours decoratively.
- Commits: conventional format (`feat:`, `fix:`, `docs:`, `test:`, `chore:` …).

## Lemonade facts (checked 2026-11-16 against v2026.46.2)

- Default base URL `http://localhost:13305/v1` (port 13305, not 8000).
- `GET /v1/health`, `GET /v1/models?show_all=true`, `GET /v1/stats` (server-wide),
  `GET /v1/system-info`, `GET /v1/downloads`.
- `POST /v1/chat/completions` (OpenAI format; images as `image_url` data URLs; streamed
  with `stream_options.include_usage`). Responses carry per-response `timings` and separate
  `reasoning_content`. `enable_thinking: false` turns reasoning off.
- `POST /v1/load` and `/v1/unload` take `{"model_name": ...}`. `/load` and chat **download
  a missing model implicitly**. `POST /v1/pull` with `stream: true, subscribe: false`
  starts a server-owned download.
- Errors: `{"error": {"message", "code"}}` or `{"error": "..."}`; `model_not_found` is 404.
- Optional auth: `Authorization: Bearer $LEMONADE_API_KEY`.
- Documents chat, completions, embeddings, reranking, transcription, TTS, audio generation,
  and image generation/edit endpoints. **No video endpoint.**
- Docs: https://lemonade-server.ai/docs/ and `docs/api/` in `lemonade-sdk/lemonade`.
  Re-check before extending the adapter.

## Roadmap

Full version in `docs/ROADMAP.md`.

- **M0 — Foundation (done):** repo, typed interfaces, API, dashboard, Lemonade discovery,
  mock backend, CI.
- **M1 — Real local inference (done):** Lemonade text and vision chat with streaming;
  per-request metrics; benchmark runner, reports, export; live telemetry.
- **M2 — First optimization:** a quality evaluator on a pinned, licensed dataset; then a
  measured quantization comparison for one text model.
- **M3 — AMD cloud execution:** SSH/ROCm remote runner behind explicit confirmation;
  QLoRA fine-tuning.
- **M4 — Selection and deployment:** constraint-based selection, manifest export, local/cloud routing.
- **M5 — More modalities:** speech and vision, then image; video only when a backend supports it.
