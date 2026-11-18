# CLAUDE.md — Antar

Antar (अन्तर) is an open-source platform for multimodal AI model optimization,
benchmarking, and cloud-to-edge deployment. Local target: AMD Lemonade. Cloud target: AMD
Instinct GPUs via ROCm. Primary development machine: an Apple Silicon Mac.

The repository is **pre-alpha**. Real local text and vision inference and benchmarking
work (Phase 1). Cloud inference through vLLM on AMD GPUs, reference-answer scoring, and the
local-versus-cloud Comparison Lab are implemented with mocked tests (Phase 2) and **have
not yet run on real AMD hardware**: never describe the cloud path as verified, and never
write a cloud benchmark number. Optimization and deployment do not exist. Read `README.md`
→ "Current implementation status" and `docs/phase2-amd-cloud.md` → "Remaining live
verification" before assuming anything else works.

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
8. **No silent cloud cost.** Antar never starts, stops, resizes, or keeps alive a paid
   resource; the operator does that with `scripts/cloud/`. `AmdCloudBackend` sends HTTP only
   to the endpoint in settings, which `CloudEndpointSettings` restricts to loopback or an
   explicitly trusted HTTPS host with an API key. Over SSH, only fixed, read-only command
   strings defined in `antar/backends/amd_cloud/` are run. Anything that uses cloud time on
   the user's behalf needs explicit confirmation (`confirm_cloud_usage` for a comparison or a
   benchmark of a cloud model)
   and respects the time budget. Never claim an instance was stopped or destroyed: Antar
   cannot know.
   **Never trigger a model download implicitly.** Lemonade's `/load` and
   `/chat/completions` download missing models on their own; every call path must go
   through `LemonadeBackend._require_downloaded` first. Downloads happen only through the
   explicit, confirmed download action.
9. **Do not push, open PRs, create remotes, or run paid cloud operations without the
   maintainer's explicit authorization** in the current session. That includes running
   `pytest -m amd_live`, the preflight, or any script against a real host.
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
  hardware/            HardwareProfile + local detection; gpu.py: remote GPU readings
  models/              ModelSpec (location, state), inventory, catalog of verified model facts
  modalities/          Catalog of tasks and metrics per modality
  backends/            RuntimeBackend interface; lemonade/, amd_cloud/, mock/
    amd_cloud/         vllm client, backend, ssh, amd_smi, preflight, feasibility, cost
  inference/           Chat types, per-request metrics, image validation, service, openai helpers
  optimization/        OptimizationJob + technique applicability (no executors yet)
  benchmarking/        Workloads, runner, report + statistics, store, job manager
  comparison/          Local-vs-cloud: config + report, manager, store, CSV/Markdown export
  evaluation/          EvaluationResult, DatasetRef; scoring.py: reference-answer scoring
  orchestration/       ExperimentRecord + filesystem store
  deployment/          DeploymentManifest, RoutingPolicy
apps/api/antar_api/    FastAPI app (thin handlers over antar/)
apps/cli/antar_cli/    Typer CLI
apps/web/              React + TypeScript + Vite + Tailwind v4 dashboard
configs/               Example YAML for every typed spec (validated by tests)
scripts/cloud/         Operator scripts for the AMD host (run by a person, never by Antar)
tests/unit, tests/integration
docs/                  architecture, installation, cloud, developer-guide, benchmarks, challenge
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
uv run pytest -m amd_live -s                          # real vLLM endpoint; needs authorization
uv run antar cloud-status                             # endpoint + GPU readings
uv run antar cloud-preflight                          # read-only host check over SSH
uv run antar cloud-estimate Qwen/Qwen3-32B --gpu-memory-gb 192
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
- The browser never calls Lemonade or vLLM; requests name a configured backend, never a
  URL. No request, prompt, or model output may become an HTTP destination or a shell
  command.
- vLLM reports no per-response timings. Leave backend-reported fields `None` for the cloud
  backend; never fill them from Antar's clock. The rate to compare across backends is the
  decode rate (`decode_tokens_per_second`), which is computed on Antar's clock for all.
- GPU readings from `amd-smi` are device-level. Never present them as per-model or
  per-request, and never sum across GPUs unless every GPU reported the value.
- A local-versus-cloud comparison is never hardware-normalized. Keep the caveats attached.
- The model catalog (`antar/models/catalog.py`) holds only facts read from the model's
  repository, with the date. Unknown models stay unclassified.
- Cost figures are arithmetic on operator-entered numbers. There is no billing API.
- Running model-written code (`allow_code_execution`) stays off by default.
- Tests replace SSH with a `RemoteRunner` fake and vLLM with `httpx.MockTransport`.
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

### Lemonade cloud providers (exercised 2026-11-18 against v2026.46.2)

Experimental in Lemonade. Exercised against the real local server with a stand-in
OpenAI-compatible server on loopback — not vLLM, no model.

- `POST /v1/install` with `{"backend": "cloud", "provider", "base_url"}` registers a
  provider; `POST /v1/uninstall` with `{"backend": "cloud", "provider"}` removes it.
- `POST /v1/cloud/auth` with `{"provider", "api_key"}` stores a key in Lemonade's memory
  only. For an `http://` base URL it returns 400 `insecure_http_requires_opt_in` unless
  `allow_insecure_http: true` is sent.
- `GET /v1/system-info` lists `cloud.providers[]` (`name`, `base_url`, `env_var_set`,
  `runtime_key_set`, `models_discovered`, `allow_insecure_http`, `warnings`).
- Discovered models appear in `/v1/models` as `<provider>.<upstream id>` with
  `recipe: "cloud"`, `cloud_provider`, and `downloaded: true`, and in `/v1/health` as loaded
  with `pid: 0`. Lemonade assigns labels (`cloud`, `chat`, and `vision` for the stand-in's
  model) itself.
- Chat, streaming, and an `image_url` content part were relayed. Lemonade forwards
  `enable_thinking` upstream as `chat_template_kwargs` plus `reasoning_effort`. Relayed
  responses carry `usage` but no `timings`.
- Antar's provider name is `antaramd`. Not tested against real vLLM.

## vLLM / AMD facts (checked 2026-11-18 against the docs; NOT yet verified live)

- Image: `vllm/vllm-openai-rocm`. Pinned default `v0.34.0-rocm100`, digest
  `sha256:3cb773d23f063afa86291ef75773cdd486154ddea94c213300f4ed7cc42b7af1`, built on ROCm
  10.0; needs Docker 23+. Host driver compatibility is unverified.
- Official ROCm docker flags: `--group-add=video --cap-add=SYS_PTRACE --security-opt
  seccomp=unconfined --device /dev/kfd --device /dev/dri --ipc=host`. Never `--privileged`.
- Endpoints: `/health` (503 while loading), `/version`, `/metrics` at the server root;
  `/v1/models`, `/v1/chat/completions` under `/v1`. `VLLM_API_KEY` guards `/v1` only.
- Images use OpenAI `image_url` parts; several per message are allowed up to
  `--limit-mm-per-prompt.image N`.
- Reasoning is returned as `reasoning` (formerly `reasoning_content`); the adapter reads
  both. `--reasoning-parser qwen3` for Qwen3.
- No per-response timings, only `usage`.
- `amd-smi static|metric|version --json` are documented commands. **The JSON key names are
  not documented**; the parser's key names are unconfirmed.
- Not on the pages read, so assumed and to be confirmed live: the `/v1/models` entry shape
  (`id`, `root`, `max_model_len`), the 401 body, and `chat_template_kwargs:
  {"enable_thinking": false}` as the per-request thinking switch.
- Model facts in the catalog were read from Hugging Face on 2026-11-18.
- Docs: https://docs.vllm.ai/en/stable/, https://rocm.docs.amd.com/. Re-check before
  extending the adapter, and update this section after the first live run.

## Roadmap

Full version in `docs/ROADMAP.md`.

- **M0 — Foundation (done):** repo, typed interfaces, API, dashboard, Lemonade discovery,
  mock backend, CI.
- **M1 — Real local inference (done):** Lemonade text and vision chat with streaming;
  per-request metrics; benchmark runner, reports, export; live telemetry.
- **Phase 2 — AMD cloud inference and comparison (implemented, awaiting live
  verification):** vLLM adapter, host scripts and preflight, GPU readings, feasibility,
  scoring, Comparison Lab, cost controls, Lemonade provider registration.
- **Phase 3 (proposed):** live verification first; then a measured quantization comparison
  scored on both sides; larger licensed datasets; concurrency benchmarks; QLoRA on the
  cloud host; routing.
- **M2 — First optimization:** a measured quantization comparison for one text model; a
  quality evaluator on a pinned, licensed dataset.
- **M3 — AMD cloud training:** QLoRA fine-tuning on the ROCm host behind explicit
  confirmation.
- **M4 — Selection and deployment:** constraint-based selection, manifest export, local/cloud routing.
- **M5 — More modalities:** speech and vision, then image; video only when a backend supports it.
