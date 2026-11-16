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

## M2 — First optimization

- A quality evaluator for one text task on a pinned dataset with a recorded license.
- Quantization comparison: several quantization levels of one model, each benchmarked for
  speed and evaluated for quality against the same baseline.
- Experiment records written by the pipeline, linking baseline and candidate reports.
- A larger, versioned prompt set, and a way to load a custom one.
- Linux GPU enumeration and telemetry (AMD first).

## M3 — AMD cloud execution

- Remote runner over SSH to a user-provisioned ROCm host, behind explicit confirmation.
- ROCm environment check (versions, devices) before any job starts.
- LoRA / QLoRA fine-tuning for text models through PEFT.
- Cost and duration surfaced before and after each remote job.

## M4 — Selection and deployment

- Constraint-based selection among measured candidates.
- Deployment manifest export, including artifact digests.
- Local/cloud routing driven by measured latency and memory, not heuristics.

## M5 — More modalities

- Speech (transcription first: word error rate, real-time factor).
- Vision quality evaluation on a labelled dataset.
- Image generation.
- Video only once a supported backend exists. Lemonade documents none today.

## Not planned

- Reimplementing model serving, download management, or engine selection that Lemonade
  already provides.
- Hosted or multi-tenant operation. Antar is a local developer tool; the API has no
  authentication and binds to localhost.
