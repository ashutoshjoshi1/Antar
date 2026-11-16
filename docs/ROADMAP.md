# Roadmap

Milestones are ordered by dependency, not by date. Each one ends in something that runs
and can be verified; none is "done" until its claims are backed by tests or recorded
experiments. This is a plan, not a promise.

## M0 — Foundation (complete)

- Monorepo, typed interfaces, configuration, CI.
- API: health, system, backends, models, capabilities, settings, experiments.
- Local hardware detection; Lemonade connectivity and model discovery; mock backend.
- Dashboard with live Overview, Models, Hardware, and Settings.

## M1 — First real measurement

The smallest slice that produces a genuine number.

- Lemonade text chat adapter (`POST /v1/chat/completions`), streaming for time to first token.
- Performance benchmark runner: time to first token, tokens per second, peak memory.
- Runner writes an `ExperimentRecord`; Benchmarks page charts it.
- `antar benchmark` CLI command.
- Linux GPU enumeration (AMD first), verified on real hardware.

## M2 — First optimization

- Quality evaluator for one text task on a pinned dataset with a recorded license.
- Quantization comparison: several quantization levels of one model, baseline versus each.
- Baseline-versus-candidate report export.

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
- Vision-language models.
- Image generation.
- Video only once a supported backend exists. Lemonade documents none today.

## Not planned

- Reimplementing model serving, download management, or engine selection that Lemonade
  already provides.
- Hosted or multi-tenant operation. Antar is a local developer tool; the API has no
  authentication and binds to localhost.
