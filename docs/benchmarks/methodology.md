# Benchmark and experiment methodology

> No benchmark runner or evaluator exists yet. This document defines the record format,
> which is implemented, and the measurement rules future runners must follow. There are no
> results in this repository.

## The experiment record

Every experiment is one `ExperimentRecord` (`antar/orchestration/experiment.py`), stored as
`<experiments_dir>/<id>.json`.

| Field | Purpose |
|---|---|
| `schema_version` | Format version, for migrating old records |
| `id`, `name` | Stable identifier (`[a-z0-9_-]`) and a readable name |
| `model.id`, `model.revision` | The exact model. Pin a commit hash, not `main` |
| `dataset.name`, `.version`, `.license`, `.split`, `.num_samples` | The exact data, and the terms it is used under |
| `hardware` | Full `HardwareProfile` of the machine that ran it |
| `backend`, `runtime_version` | Which runtime, and the version it reported at run time |
| `optimization` | Ordered techniques and their parameters |
| `seed` | Random seed, where the workload has one |
| `baseline`, `optimized` | `EvaluationResult` before and after |
| `artifacts` | Produced files with SHA-256 digests and sizes |
| `started_at`, `finished_at` | UTC timestamps |

Each `EvaluationResult` carries its own `methodology` text, its `metrics`, and a
`simulated` flag.

## Rules

1. **A record describes what happened.** Fields the run did not determine stay empty.
   Nothing is backfilled or estimated.
2. **Baseline and optimized are measured the same way**: same hardware, backend, dataset
   slice, prompts, and generation settings. A difference in setup is a different experiment.
3. **Metrics must belong to the modality.** `EvaluationResult` rejects metric keys that the
   modality catalog does not define for that modality, and rejects non-finite values.
4. **Quality needs a dataset.** A quality metric without a pinned dataset and license is
   not reportable.
5. **Simulated stays simulated.** Anything derived from the mock backend has
   `simulated=true`, and the dashboard labels it. Simulated records are for exercising the
   pipeline, never for comparison.
6. **Methodology is written down**: warmup runs, measured runs, how values were aggregated,
   and anything that could affect the number (thermal state, other load, power mode).

## Metrics by modality

Defined in `antar/modalities/catalog.py` and served by `GET /api/v1/capabilities`.

| Modality | Quality | Performance |
|---|---|---|
| Text | Task accuracy, perplexity, valid tool-call rate | Time to first token, tokens/s, peak memory |
| Vision | VQA accuracy, character error rate (OCR) | Time to first token, tokens/s, peak memory |
| Speech | Word error rate, round-trip TTS intelligibility | Real-time factor, latency, peak memory |
| Image | CLIP score, FID, LPIPS | Seconds per image, peak memory |
| Video | FVD, CLIP score, temporal consistency | Seconds per frame, peak memory |

Metrics are not interchangeable across modalities: word error rate means nothing for an
image model, and FID needs far more samples than a quick run produces. Evaluators will
document their sample-size requirements when they are implemented.

## Planned measurement procedure (M1)

For the first runner — text chat performance through Lemonade:

1. Record the hardware profile and the Lemonade version from `/v1/health`.
2. Load the model and run the configured warmup requests, which are discarded.
3. Run the measured requests with a fixed prompt set, seed, and token limit.
4. Record time to first token and tokens per second per request; report the median and
   spread, not the best run.
5. Record peak memory as reported by the runtime, noting the source.
6. Write the record. Never overwrite an existing id.

## Comparing results

The dashboard charts each experiment's relative change from its own baseline, coloured by
whether the metric moved in its better direction. Results from different hardware,
datasets, or methodologies should not be placed side by side as if they were comparable.
