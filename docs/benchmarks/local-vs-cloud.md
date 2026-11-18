# Local versus cloud: Comparison Lab methodology

> There are no results in this repository. Comparison reports are written to
> `data/comparisons/`, which is git-ignored. No comparison has been run against a real AMD
> GPU yet.

## What a comparison is, and is not

A comparison runs the same workloads on one local model and one cloud model and puts the
two sets of measurements side by side.

It answers "what does a user get from each place". It does **not** answer "which hardware
is faster". The two sides differ in model size, weight precision, hardware, and network
path all at once. Nothing is hardware-normalized, and the report says so at the top, in its
caveats, and in every export.

## Procedure

`ComparisonManager` (`antar/comparison/manager.py`):

1. Requires `confirm_cloud_usage: true`, because the run keeps a paid instance busy.
2. Validates both sides before anything runs: the local model must not be a cloud model,
   the cloud model must not be a local one, each must be present and able to run the chosen
   workloads.
3. Runs the **local side first**, then the **cloud side**. Each side is an ordinary
   benchmark run (`BenchmarkRunner`), so everything in the
   [benchmark methodology](methodology.md) applies: one request at a time, streamed,
   `warmup_runs` unmeasured requests per workload, then `measured_runs` passes over every
   prompt.
4. Both sides get identical prompts in identical order, and identical `max_tokens`,
   `temperature`, `seed`, and thinking setting. Only the model differs.
5. If the local side fails, the cloud side is not run, so no cloud time is spent on half a
   comparison.
6. While the cloud side runs, samples the cloud GPUs at the configured interval.
7. Measures the path to the cloud endpoint, builds the report, and saves it.

Neither model is reloaded. vLLM serves one model chosen at start, so there is nothing to
reload on that side, and the local side is left as loaded to match.

A comparison shares one slot with benchmarks: only one measuring job runs at a time, and
chat and model actions are refused with 409 while it runs.

### Stopping

- **Cancel** aborts the request in flight and saves what finished, with status
  `cancelled`.
- **Time budget.** A comparison is stopped after `time_budget_minutes`, or
  `cloud_cost.max_experiment_minutes` (30 by default) when none is given. The report says
  it was stopped at the budget.

## What is measured, and by whom

Every row in a report carries a `scope` and a `measured_by`. `null` means not available;
it is never zero.

| Row | Unit | Scope | Measured by |
|---|---|---|---|
| End-to-end latency, median | ms | end-to-end | Antar API |
| End-to-end latency, p95 | ms | end-to-end | Antar API |
| Time to first token, median | ms | end-to-end | Antar API |
| Tokens per second after the first token, median | tok/s | end-to-end | Antar API |
| First request of the run | ms | end-to-end | Antar API |
| Tokens per second, backend-reported, median | tok/s | model | backend |
| Prompt processing, backend-reported, median | ms | model | backend |
| Generation time, backend-reported, median | ms | model | backend |
| Output tokens, mean | tokens | model | backend |
| Input tokens, median | tokens | model | backend |
| Error rate | ratio | reliability | Antar API |
| Automatic score, mean | ratio | quality | Antar scorer |
| Valid JSON rate | ratio | quality | Antar scorer |

Rows are produced for each workload and for all workloads together.

**End-to-end** rows are what a user waits for. They are timed by the Antar API around the
HTTP call and include the path to the backend: loopback for the local side, an SSH tunnel
for the cloud side.

**Model** rows are the backend's own account of one response. Lemonade's llama.cpp engine
reports per-response timings. **vLLM reports token counts but no per-response timings**, so
the backend-reported speed, prompt processing, and generation time rows are unavailable on
the cloud side. Antar does not derive them from its own clock and present them as
backend-reported.

### The rate to compare across backends

"Tokens per second after the first token" is output tokens divided by the time between the
first streamed chunk and the end of the response, both seen by the Antar API. It is
computed the same way for every backend, which makes it the one generation rate that can be
placed side by side. It is unavailable when the token count or first-chunk time is missing,
or when the response arrived in a single chunk. Because it is observed through the stream,
it includes any buffering in the path.

### Time to first token

The client-observed value is the time until the first streamed text reached the Antar API.
A backend-reported time to first token is not available from either backend per response.
Lemonade's prompt processing time is the closest backend figure and is shown as its own
row.

### Transport

After the runs, Antar times five `GET /health` round trips to the cloud endpoint and
records the samples and their median. No inference is involved, so this approximates the
cost of the path alone. It is context for the end-to-end rows, not a correction: Antar does
not subtract it from anything.

### Cold and warm

Statistics cover measured requests only. Warm-up requests are excluded. The very first
request each side served in the run is reported in its own row, outside the statistics,
because it may include one-time work such as kernel compilation on the GPU.

Model load time and weight download time are not part of a comparison. The scripts record
them on the host; see
[download, load, and inference time](../cloud/rocm-vllm.md#download-time-load-time-inference-time).

### GPU readings

When an SSH host is configured, Antar samples `amd-smi` during the cloud side, no more
often than `gpu_poll_interval_seconds`. The report summarizes: GPU count and names, total
memory, peak memory used, mean and peak utilization, peak power, driver and ROCm versions,
and the number of samples.

These are **device-level** readings for the whole GPU. They are not per-model or
per-request, and peak memory mostly reflects vLLM's up-front reservation, not what a
request needed. A sum across GPUs is reported only when every GPU reported the value.
Anything `amd-smi` did not report is listed as unavailable with the reason. Without an SSH
host there is no GPU summary.

The local side records which local telemetry could not be read, as in a normal benchmark.
Per-request memory is unavailable on both sides.

### Cloud usage

The report records the seconds the cloud side took and, if you entered an hourly price,
that duration multiplied by the price. This is the cost of the time this run kept the
instance busy. The instance bills for all the time it exists.

## Quality evaluation

### Scored workloads

Six workloads have a reference answer for every prompt and are scored automatically
(`antar/evaluation/scoring.py`). The score of a workload is the mean over its measured,
successful responses.

| Workload | Prompts | Rule |
|---|---|---|
| `qa_exact` | 6 | Exact match, or the final number |
| `reasoning_basic` | 6 | The final number, or exact match for yes/no |
| `json_schema` | 3 | Required fields, their JSON types, and extracted values |
| `code_tests` | 3 | Share of unit tests passed. Only when code execution is enabled |
| `vision_reference` | 6 | Exact match, or the final number, about bundled images |
| `ocr_basic` | 3 | Exact match, or the final number, read from a document image |

The rules, precisely:

- **Exact.** After trimming whitespace, surrounding quotes, asterisks, and trailing
  punctuation, and ignoring case, the response must equal the reference. An answer buried
  in a sentence does not match; the prompts ask for the answer alone.
- **Number.** The last number in the response is taken as the answer, so shown working does
  not count against it. Thousands separators are accepted.
- **JSON fields.** The response (a Markdown code fence around it is allowed) must parse as
  a JSON object, every required key must have the stated type, and any key with a reference
  value must equal it. All or nothing.
- **Unit tests.** The response is run in a separate Python process and each assert is
  tried; the score is the share that pass.

Each scored run records its `score`, `score_method`, and a `score_detail` sentence saying
why.

A score says the response matched the reference by that rule. It is not a general judgement
of quality, and these sets are small smoke tests, not a benchmark of a model.

### Provenance and licence

The scored workloads were written for Antar, contain no third-party content, and are CC0.
Each workload records its `license` and `provenance`. Every reference is either a
checkable fact or true by construction: the image references are the constants that
`scripts/generate_benchmark_images.py` draws (colours, counts, and the text in the document
and diagram images), so they are true of the bundled images. No labels were invented.

Editing a prompt or a reference requires bumping the workload's `version`. Two reports are
comparable only when workload ids and versions match.

### Running model-written code

`code_tests` runs code a model wrote. That is off by default
(`allow_code_execution: false`), and when off, those responses are recorded as not scored.
When enabled, the code runs in a separate Python process in a temporary directory with an
empty environment and a time limit. **That contains mistakes, not malice. It is not a
security sandbox.** Enable it only for models and prompts you are willing to run code from.
The code runs as your user with file and network access. The tests are tallied in the same
process as the code, so code written to cheat could report passes it did not earn; a
unit-test score is trustworthy only for a model that is not trying to game it.

### Manual review

`general_qa`, `code_generation`, and `vision_basic` have open-ended answers and no
automatic score. Each run has `manual_score` (1 to 5) and `manual_notes`, filled in by a
person. Antar never computes them. `structured_json` only checks that the reply parses.

### LLM-as-judge

Not implemented. A judge model's scores depend on the judge, its prompt, and its own
errors; they drift between judge versions and can favour answers that resemble the judge's
own style. For the questions Phase 2 asks, objective checks were possible, so those were
built first. If a judge is added later it would need a pinned judge model and revision, a
published prompt, its scores stored separately from the objective ones and labelled as
judged, and agreement measured against a human-reviewed sample before any use. It would
never replace the objective scores.

## Exports

`GET /api/v1/comparisons/{id}/export?format=json|csv|md`

- **JSON**: the complete report.
- **CSV**: one row per request from both sides, with a `side` column. Unavailable values
  are empty cells, never zero.
- **Markdown**: what ran, result tables per workload with scope and measured-by columns,
  Mermaid bar charts for the two rows comparable across backends (drawn only when both
  sides have the value), cloud hardware and usage, methodology, and limitations.

## What a report records

| Field | Content | Source |
|---|---|---|
| `id`, `started_at`, `finished_at`, `status`, `failure` | Identity and outcome | Antar |
| `simulated` | True if either side was the mock backend | Antar |
| `antar_version`, `git_commit` | The code that ran | Antar |
| `config` | Both targets, workloads, warm-up and measured counts, generation settings, time budget | The request |
| `local`, `cloud` | A full benchmark report per side: every request with its metrics, response, and score; per-workload statistics; the prompts as sent, with workload versions; model id, revision, precision, parameter count, context length, runtime; backend version (the vLLM version for the cloud side); where it ran; missing telemetry | Measured, or reported by the backend |
| `cloud.remote_gpus` | The GPU sample taken before the cloud side | `amd-smi` |
| `local.hardware`, `cloud.hardware` | The machine the Antar API ran on | Detected locally |
| `gpu` | The GPU summary, including driver and ROCm versions | `amd-smi` |
| `transport` | Health round-trip samples and median | Antar API |
| `usage` | Cloud seconds, the hourly price, the estimate | Measured duration; **price entered by the operator** |
| `vllm_image` | The container image | **Declared by the operator** in `cloud.vllm_image` |
| `lemonade_version` | Lemonade's version | Reported by Lemonade |
| `rows` | The side-by-side table | Derived from the two reports |
| `caveats` | The limitations, stored with the report | Antar |

Two fields are not measured. `vllm_image` is whatever you wrote in the configuration; the
image digest actually used is in `vllm-deployment.json` on the host. A model `revision` is
recorded only when you declared or requested one; vLLM's model list does not report it.

To reproduce a comparison, another developer needs the report's `config`, the same Antar
commit, the same model revisions and image, and comparable hardware on both sides. The
hardware is recorded; it cannot be reproduced by the report.

## Caveats

Stored in every report and shown wherever it is rendered:

- Not a hardware-normalized comparison.
- End-to-end times include the path to each backend.
- Backend-reported timings exist only where the backend reports them per response.
- Statistics cover measured requests only; the first request is shown separately.
- Automatic scores compare a response with a reference by a fixed rule.
- GPU readings are device-level and sampled at intervals.

Also bear in mind: requests run one at a time, so nothing here describes throughput under
concurrent load; the prompt sets are small; and a single run on a shared or thermally
limited machine can vary. Repeat runs and report the spread before drawing a conclusion.
