# Roadmap

Milestones are ordered by dependency, not by date. Each one ends in something that runs
and can be verified; none is "done" until its claims are backed by tests or recorded
experiments. This is a plan, not a promise.

## M0 — Foundation (complete)

- Monorepo, typed interfaces, configuration, CI.
- API: health, system, backends, models, capabilities, settings, experiments.
- Local hardware detection; Lemonade connectivity and model discovery; mock backend.
- Dashboard with live Overview, Models, Hardware, and Settings.

## M1 — Real local inference (complete)

- Lemonade chat adapter: text and image understanding, streaming, cancellation.
- Model load, unload, and explicitly confirmed download; no implicit downloads.
- Per-request metrics from the backend's own response timings.
- Benchmark runner with three text workloads and a basic vision workload; cold and warm
  runs kept apart; reports with JSON and CSV export; manual review fields.
- Live telemetry with unavailable measurements labelled.
- Dashboard: Playground, Vision, Models, Benchmarks, System.

Carried over, not done: Linux GPU enumeration, which needs real AMD hardware to verify.

## Phase 2 — AMD cloud inference and comparison (implemented, awaiting live verification)

Built ahead of the first optimization, because a large-model baseline on AMD GPUs is what
the optimizations will be measured against. **Nothing in this milestone has run on real
AMD hardware yet.** It is not complete until the
[live verification checklist](phase2-amd-cloud.md#remaining-live-verification) is done.

- `amd_cloud` backend for a self-hosted vLLM server: text and vision chat, streaming,
  cancellation. Mocked tests.
- Operator scripts for the host; read-only preflight; `amd-smi` GPU readings; memory
  feasibility estimate from verified model facts.
- Endpoint allowlist, SSH tunnel, API key handling.
- Unified model registry with execution location and state.
- Reference-answer scoring and six small CC0 workloads, including image questions and OCR.
- Comparison Lab with JSON, CSV, and Markdown export; experiment history.
- Operator-entered cost estimate, time budgets, confirmation before cloud use.
- Optional registration with Lemonade's cloud routing, checked against a real Lemonade with
  a stand-in server.

What moved: the ROCm environment check and cost surfacing came forward from the old M3. The
first quality evaluator from M2 arrived in a small form (reference answers on prompt sets
written for Antar), not yet on a pinned external dataset.

## Phase 3 — proposed

In dependency order. Each step ends in something recorded.

1. **Live verification.** Run the Phase 2 checklist on a real AMD GPU host: preflight,
   image and driver compatibility, `amd-smi` key names, Qwen3 8B smoke test, text and vision
   inference, the first real local-versus-cloud reports, `pytest -m amd_live`. Fix what the
   real server contradicts. Read the host's deployment and readiness records into the
   experiment so load and download times travel with it.
2. **Quantization comparison.** Several quantization levels of one model on Lemonade, each
   benchmarked and scored with the same workloads, against the full-precision model on the
   cloud host as the quality reference. Experiment records linking the reports.
3. **Larger, licensed evaluation data.** A pinned external dataset with a recorded licence
   for at least one text task and one vision task, and a way to load a custom prompt set.
   Scores with sample sizes large enough to state uncertainty.
4. **Concurrency benchmarks.** Throughput and latency under concurrent load on the cloud
   side, which the current one-at-a-time runner does not measure, using vLLM's own metrics
   endpoint where it helps.
5. **QLoRA fine-tuning on the cloud host** through PEFT, behind explicit confirmation, with
   cost and duration shown before and after.
6. **Routing.** A local-or-cloud decision per request driven by the measured latency,
   quality, and cost, not by heuristics.
7. Linux GPU enumeration and local AMD telemetry, verified on the same hardware.

## M2 — First optimization

- Quantization comparison: several quantization levels of one model, each benchmarked for
  speed and evaluated for quality against the same baseline. (Phase 3, step 2.)
- Experiment records written by the pipeline, linking baseline and candidate reports.
- A quality evaluator on a pinned dataset with a recorded license, and a larger, versioned
  prompt set with a way to load a custom one. (Phase 3, step 3.)
- Linux GPU enumeration and telemetry (AMD first).

## M3 — AMD cloud training

- LoRA / QLoRA fine-tuning for text models through PEFT on the user-provisioned ROCm host,
  behind explicit confirmation. (Phase 3, step 5.)
- Cost and duration surfaced before and after each remote job.

## M4 — Selection and deployment

- Constraint-based selection among measured candidates.
- Deployment manifest export, including artifact digests.
- Local/cloud routing driven by measured latency, quality, and cost, not heuristics.

## M5 — More modalities

- Speech (transcription first: word error rate, real-time factor), locally through
  Lemonade's documented endpoints, and in the cloud through a specialized worker; see the
  [future cloud-worker interface](architecture/cloud-execution.md#future-cloud-workers).
- Vision quality evaluation on a labelled dataset.
- Image generation.
- Video only once a supported backend exists. Lemonade documents none today.

## Not planned

- Reimplementing model serving, download management, or engine selection that Lemonade
  already provides.
- Provisioning, starting, stopping, or billing cloud machines. Antar talks to a host you
  run and estimates cost from numbers you enter.
- Hosted or multi-tenant operation. Antar is a local developer tool; the API has no
  authentication and binds to localhost.
