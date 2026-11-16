# Antar (अन्तर)

**Cloud-scale intelligence. Local freedom.**

Antar is an open-source platform for optimizing, benchmarking, and deploying multimodal AI
models across the distance between cloud GPUs and the device in front of you. *Antar* is
Sanskrit for "difference" or "the space between" — the gap this project exists to close.

> **Status: pre-alpha.** Real local inference works today: text chat with streaming, image
> understanding, and repeatable performance benchmarks, all through Lemonade. **No
> optimization, quality evaluation, cloud execution, or deployment exists yet.** See
> [Current implementation status](#current-implementation-status) for exactly what is and is
> not built.

## The problem

The most capable models need more memory and compute than a laptop or edge device has.
Developers who want to run them locally face a pile of manual work: guess which techniques
apply (quantization? distillation? adapters?), try them one at a time, and hope quality
survived. Results are rarely measured the same way twice, so they are hard to trust or
reproduce. And when a model simply cannot fit, there is no principled way to fall back to
the cloud.

Antar's goal is to turn that into one measured, reproducible pipeline:

1. Accept a model and a target workload.
2. Identify the available cloud and local hardware.
3. Measure baseline quality and performance.
4. Determine which optimization techniques apply.
5. Run the selected experiments.
6. Benchmark the optimized candidates.
7. Compare quality, latency, throughput, and memory.
8. Select a configuration that satisfies your constraints.
9. Export reproducible deployment artifacts and reports.

## Architecture

```mermaid
flowchart LR
    subgraph Clients
        WEB["Dashboard<br/>React + Vite"]
        CLI["CLI<br/>antar"]
    end

    API["FastAPI<br/>/api/v1"]

    subgraph Core["antar (Python library)"]
        HW["hardware<br/>detection + profiles"]
        INV["models<br/>inventory"]
        INF["inference<br/>chat + streaming + images"]
        BEN["benchmarking<br/>runner + reports"]
        CAT["modalities<br/>tasks + metrics"]
        OPT["optimization<br/>job spec · planned executors"]
        EXP["orchestration<br/>experiment records"]
        DEP["deployment<br/>manifests · planned routing"]
        REG["backends<br/>RuntimeBackend interface"]
    end

    subgraph Backends
        LEM["Lemonade<br/>local inference"]
        AMD["AMD cloud<br/>ROCm · interface only"]
        MOCK["Mock<br/>simulated, offline"]
    end

    WEB --> API
    CLI --> Core
    API --> Core
    INV --> REG
    INF --> REG
    BEN --> REG
    OPT -.-> REG
    DEP -.-> REG
    REG --> LEM
    REG -.-> AMD
    REG --> MOCK
```

Solid lines work today; dashed lines are defined interfaces with no execution behind them
yet. More detail in [docs/architecture/overview.md](docs/architecture/overview.md).

## Why AMD Lemonade is central

[Lemonade](https://lemonade-server.ai) is the local half of the cloud-to-edge story. It is
a local AI server with an OpenAI-compatible API that already manages model download,
loading, and hardware-specific inference engines across text, vision, speech, and image
models. Antar deliberately does **not** reimplement any of that. Instead it treats Lemonade
as the deployment target: the thing an optimized model must run well *on*, and the runtime
whose measured behaviour decides whether an optimization was worth it.

The cloud half is AMD Instinct GPUs through ROCm, where compute-heavy work (fine-tuning,
distillation, large-model baselines) is meant to run. Antar stays portable: nothing in the
base install is AMD-specific, and local development works on an Apple Silicon Mac with no
cloud access.

## Key capabilities

| Capability | State |
|---|---|
| Lemonade connectivity, model discovery, load, and confirmed download | Working |
| Text chat with streaming, cancellation, and separate reasoning output | Working |
| Image understanding with a vision-language model | Working |
| Per-request metrics from the backend's own timings | Working |
| Benchmark runner: three text workloads and a basic vision workload | Working |
| Benchmark reports with JSON and CSV export, manual review, and comparison checks | Working |
| Live telemetry, with unavailable measurements labelled | Working |
| Local hardware detection | Working (GPU enumeration: macOS only) |
| Explicit capability discovery per backend, including what is *not* supported | Working |
| Mock backend for offline development | Working (text only, clearly simulated) |
| Quality evaluators (accuracy, WER, and so on) | Not built |
| Optimization executors (LoRA/QLoRA, distillation, quantization) | Not built |
| AMD cloud remote execution | Not built (config validation only) |
| Local/cloud routing and deployment | Not built |
| Speech, image generation, video | Not built (interfaces only) |

## Installation

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 22+, and
[pnpm](https://pnpm.io). A GPU is not required.

```bash
git clone https://github.com/ashutoshjoshi1/Antar.git
cd Antar
uv sync                          # backend (no PyTorch, no GPU stack)
cd apps/web && pnpm install      # dashboard
```

Inference needs [Lemonade](https://lemonade-server.ai) running locally with at least one
model downloaded. Antar looks for it at `http://localhost:13305/v1`; without it the
dashboard still runs and says plainly that the server is unreachable. Antar never downloads
a model unless you confirm it. Full instructions:
[local inference walkthrough](docs/phase1-local-inference.md),
[local setup](docs/installation/local.md), [AMD cloud setup](docs/installation/amd-cloud.md).

## Quick start

```bash
# Terminal 1: API on http://localhost:8080
uv run antar serve

# Terminal 2: dashboard on http://localhost:5173
cd apps/web && pnpm dev
```

From the command line:

```bash
uv run antar system                       # detected hardware, as JSON
uv run antar backends                     # is Lemonade reachable?
uv run antar models                       # models reported by reachable backends
uv run antar mock-generate "hello"        # simulated output from the mock backend

# Real inference through the API (the model must already be downloaded in Lemonade)
curl -N localhost:8080/api/v1/inference/chat/stream -H 'Content-Type: application/json' \
  -d '{"model": "Qwen3-1.7B-GGUF", "messages": [{"role": "user", "content": "Say hello."}]}'
```

Then open the dashboard: **Playground** for text, **Vision** for images, **Benchmarks** to
measure a model. API reference: [docs/api.md](docs/api.md), or `http://localhost:8080/docs`.

## Current implementation status

Antar is honest about its own state by design: the API reports support levels
(`supported`, `documented`, `planned`, `unsupported`) and the dashboard labels anything
unfinished as "Not built yet".

**Works today**

- Text and image-understanding chat through Lemonade, streamed, cancellable, with the
  measurements Lemonade reports for each response
- Model explorer: what is downloaded and loaded, with load, unload, and confirmed download
- Benchmark runner with four built-in workloads, cold-start measurement, saved reports,
  JSON/CSV export, manual review of answers, and a check for unfair comparisons
- System page with live telemetry
- Verified against a real Lemonade 2026.46.2 server on an Apple M3 Pro, including opt-in
  live tests (`uv run pytest -m lemonade_live`)
- 204 backend tests and 52 frontend tests; ruff, mypy (strict), ESLint, and `tsc` in CI

**Does not exist yet**

- Any optimization, quality evaluation, cloud execution, or deployment. The Optimization
  page builds and validates a job specification only.
- Quality scores. Benchmarks measure speed and reliability; whether an answer is *good* is
  judged by a person. There are no benchmark numbers in this repository.
- Per-request memory, GPU utilization, or power figures. Where the operating system does
  not expose them, Antar says "unavailable".
- Speech, image generation, and video. Lemonade documents no video endpoint at all.

## Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md). The next milestone is the first optimization: a
quality evaluator on a pinned dataset, then a measured comparison of quantization levels of
one model.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[developer guide](docs/developer-guide/setup.md). Two rules matter more than any style
guide: never commit a number that was not measured, and never claim a capability that does
not work. Please report security issues privately, per [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE). Antar is an independent open-source project and is not affiliated with or
endorsed by AMD. AMD, Instinct, ROCm, and Ryzen are trademarks of Advanced Micro Devices,
Inc.
