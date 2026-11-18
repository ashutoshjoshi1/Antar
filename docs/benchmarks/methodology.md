# Benchmark and experiment methodology

> The benchmark runner is implemented. It measures how fast and how reliably a model
> answers, and, for six small workloads with reference answers, whether the answer matched
> the reference. Open-ended answers are judged by a person. There are no results in this
> repository; reports are written to a git-ignored directory.
>
> Comparing a local model with a cloud model has its own page:
> [local versus cloud](local-vs-cloud.md).

## Performance benchmarks

### Procedure

`BenchmarkRunner` (`antar/benchmarking/runner.py`) does the following, strictly one request
at a time:

1. Refuse to start unless the model is already downloaded (or, for a cloud model, being
   served), and has vision support if a vision workload is selected.
2. Capture the hardware profile, backend version, model checkpoint, precision, revision,
   and parameter count where known, where the model runs, the Antar version and git commit,
   and the list of telemetry that is unavailable. For a cloud model, also a GPU sample from
   the remote host when an SSH host is configured.
3. Load the model. With `load_policy: reload` it is unloaded first; the load is timed and
   the first request after it is recorded as the **cold** run.
4. For each workload: send `warmup_runs` unmeasured requests, then `measured_runs` passes
   over every prompt.
5. Record every request individually, compute statistics, and save the report.

Requests are streamed so the time to the first chunk can be observed. A request that fails
is recorded with its error and the run continues. If loading fails, the run fails. A
response to a prompt that has a reference answer is scored as soon as it arrives.

### What is measured, and by whom

| Metric | Source | Notes |
|---|---|---|
| `latency_ms` | Antar API clock | Whole request: transport, prompt processing, generation |
| `first_chunk_ms` | Antar API clock | Until the first streamed text arrived. Not the backend's time to first token |
| `tokens_per_second` | Backend, this response | llama.cpp `timings.predicted_per_second`: generation only |
| `prompt_processing_ms`, `generation_ms` | Backend, this response | llama.cpp `timings` |
| `prompt_tokens`, `completion_tokens`, `cached_prompt_tokens` | Backend, this response | `usage` |
| Decode rate (`decode_tokens_per_second_median`) | Antar API clock and the backend's token count | Output tokens over the time after the first chunk. Computed the same way for every backend |
| `score` | Antar scorer | Only for prompts with a reference answer |

The backend-reported timings come from Lemonade's llama.cpp engine. vLLM reports token
counts but no per-response timings, so for the `amd_cloud` backend `tokens_per_second`,
`prompt_processing_ms`, and `generation_ms` are unavailable. The decode rate exists so
that one generation rate can be compared across backends.

Lemonade's `/v1/stats` is **not** used: it reports the server's most recent request from
any client, so it cannot be attributed to a particular request. Antar measures on the same
machine as Lemonade, so `latency_ms` includes only loopback transport; from another
machine it would include the network.

Not measured, and reported as unavailable: memory per request, and local GPU utilization,
GPU memory, and power. On macOS the model server's process memory is not readable by an
unprivileged process. For a cloud model, device-level GPU readings come from `amd-smi` on
the host; they describe the whole GPU, not the request.

### Statistics

Computed over **measured** requests that succeeded. Cold and warm-up requests never enter
them.

- Mean and median of latency and of tokens per second.
- P95 latency by the nearest-rank method: the smallest value with at least 95% of values
  at or below it. With few requests, P95 is simply the slowest or second-slowest one.
- Error rate: failed measured requests over all measured requests.
- Valid-JSON rate, for the structured workload only. It checks that a reply parses as JSON
  (a Markdown code fence around it is allowed). It says nothing about whether the content
  is right.
- Accuracy: the mean automatic score over the scored responses, with the number scored.
- Median decode rate.

### Workloads

Workloads are fixed prompt sets with a version. Editing a prompt changes what is measured,
so it requires a version bump, and two reports are comparable only when workload ids and
versions match.

| Id | Prompts | Automatic check |
|---|---|---|
| `general_qa` | 4 | None |
| `code_generation` | 4 | None |
| `structured_json` | 3 | Parses as JSON |
| `vision_basic` | 3 synthetic images | None |
| `qa_exact` | 6 | Exact match or final number |
| `reasoning_basic` | 6 | Final number, or exact yes/no |
| `json_schema` | 3 | Required fields, types, and extracted values |
| `code_tests` | 3 | Unit tests, only with `allow_code_execution` |
| `vision_reference` | 6, on 4 synthetic images | Exact match or final number |
| `ocr_basic` | 3, on a synthetic document image | Exact match or final number |

These are small smoke-test sets meant to give stable timings and a basic correctness
signal, not to characterize a model. The images are generated by
`scripts/generate_benchmark_images.py` and are CC0; the scored workloads record their
licence and provenance. The scoring rules, and why running model-written code is opt-in,
are in [local versus cloud](local-vs-cloud.md#quality-evaluation).

### Comparability

Two reports can be compared directly only if they used the same workloads and versions, the
same `max_tokens`, `temperature`, `seed`, and reasoning setting, and the same hardware. The
dashboard checks these and lists every difference before showing two runs side by side.

Defaults favour comparability: temperature 0, a fixed seed, and reasoning off, because a
reasoning model spends an unpredictable number of tokens thinking. Tokens per second is
fairly insensitive to output length; latency is not, so compare latency only between runs
with the same `max_tokens`, and prefer tokens per second across models.

### Manual review

For open-ended text and image answers (`general_qa`, `code_generation`, `vision_basic`)
there is no automatic score. Each run in a report has
`manual_score` (1 to 5) and `manual_notes`, filled in by a person in the dashboard and
saved in the report. They are never computed.

### The report file

`BenchmarkReport` (`antar/benchmarking/report.py`), saved as `<benchmarks_dir>/<id>.json`:

| Field | Content |
|---|---|
| `id`, `status`, `started_at`, `finished_at` | Identity and outcome: `completed`, `cancelled`, or `failed` |
| `simulated`, `notes` | True for mock-backend runs; free-text label |
| `antar_version`, `git_commit` | The code that ran |
| `backend`, `backend_version` | For example Lemonade and its version |
| `model` | Id, checkpoint, quantization or precision, runtime, size, revision, parameter count, context length |
| `hardware` | Full hardware profile of the machine Antar ran on, including the operating system |
| `execution` | Where the model ran: `local`, `cloud`, or `mock` |
| `remote_gpus` | For a cloud run, the GPU sample taken from the host before it started |
| `config` | The exact `BenchmarkConfig`: settings, warm-up and run counts |
| `workloads` | The prompts as sent, with versions |
| `cold_start` | Load time and the first request, when measured |
| `runs` | Every request: phase, timings, tokens, response, error, automatic score and its reason, review |
| `aggregates` | Statistics per workload and overall |
| `missing_telemetry` | What could not be measured, and why |
| `failure` | The reason, if the run failed |

`examples/benchmarks/illustrative-report.json` shows the shape. It was produced by the mock
backend, is flagged `simulated`, and is not a result.

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

## Comparing results

For optimization experiments, the dashboard charts each experiment's relative change from
its own baseline, coloured by whether the metric moved in its better direction. Results from different hardware,
datasets, or methodologies should not be placed side by side as if they were comparable.
