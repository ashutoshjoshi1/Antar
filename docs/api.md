# HTTP API

Base URL `http://localhost:8080`. Interactive reference, generated from the code, is at
`/docs` while the API runs; that is the authority if this page and it disagree.

The API is a local developer tool: no authentication, CORS limited to the configured
dashboard origins. Errors are JSON `{"detail": "..."}`.

| Status | Meaning |
|---|---|
| 404 | Unknown model, benchmark, or run |
| 409 | Model not downloaded, or a benchmark or comparison is already running |
| 422 | Invalid request, missing confirmation, unsupported image, model without the needed capability |
| 502 | A backend was reached but failed the request (for example, out of memory) |
| 503 | A backend is not reachable or not configured |

## Status and discovery

| Endpoint | Returns |
|---|---|
| `GET /health` | API liveness and version |
| `GET /api/v1/backends` | Connection status of each backend, including Lemonade's version |
| `GET /api/v1/system` | Hardware profile of the API host |
| `GET /api/v1/telemetry` | Live CPU and memory, loaded models, Lemonade server counters, and what is unavailable |
| `GET /api/v1/capabilities` | Modality catalog and each backend's support levels |
| `GET /api/v1/settings` | Effective configuration, secrets redacted |

## Models

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/models` | Every model from reachable backends: where it runs (`location`), who serves it (`provider`), its `state`, size, precision, parameter count, labels |
| `GET /api/v1/models/{backend}/{model_id}` | One model |
| `POST /api/v1/models/load` | Load a downloaded model. Body `{"model": "...", "backend": "lemonade"}` |
| `POST /api/v1/models/unload` | Unload a model |
| `POST /api/v1/models/download` | Start a download. Requires `"confirm": true` |
| `GET /api/v1/models/downloads` | Downloads in progress |

`load` never downloads: a model that is not present returns 409. Cloud models cannot be
loaded, unloaded, or downloaded through the API: vLLM serves the model it was started with.

`location` is `local`, `cloud`, or `mock`. `state` is `configured`, `discovered`,
`installed`, or `loaded`; see
[the model registry](architecture/cloud-execution.md#the-model-registry).

## Inference

`POST /api/v1/inference/chat` returns the finished reply.
`POST /api/v1/inference/chat/stream` returns Server-Sent Events.

```json
{
  "backend": "lemonade",
  "model": "Qwen3-1.7B-GGUF",
  "messages": [
    {"role": "user", "content": "Describe this image.",
     "images": [{"media_type": "image/png", "data_base64": "..."}]}
  ],
  "settings": {"max_tokens": 512, "temperature": 0.7, "top_p": 0.9, "seed": 1, "enable_thinking": false}
}
```

- `backend` names a configured backend: `lemonade`, `amd_cloud`, or `mock`. URLs are not
  accepted anywhere.
- `images` is optional, user messages only, PNG, JPEG, or WebP. The declared type must
  match the file's contents, and the model must accept images. At most four images per
  message and per conversation; Lemonade accepts one per message and refuses more.
- Every `settings` field is optional except that `max_tokens` defaults to 512.

Stream events, one JSON object per `data:` line:

```
data: {"type":"delta","content":"Hel","reasoning":""}
data: {"type":"done","result":{"content":"Hello","reasoning":null,"finish_reason":"stop","metrics":{...},"simulated":false}}
data: {"type":"error","message":"...","kind":"BackendRequestError"}
```

A stream ends with exactly one `done` or `error`. Closing the connection cancels
generation in the backend.

`metrics` fields are `null` when unavailable: `latency_ms`, `first_chunk_ms` (streaming
only), `prompt_tokens`, `completion_tokens`, `cached_prompt_tokens`,
`prompt_processing_ms`, `generation_ms`, `tokens_per_second`. The last three are reported
by the backend for that response; vLLM reports none of them, so they are `null` for
`amd_cloud`.

## Benchmarks

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/benchmarks/workloads` | Built-in workloads and their prompts |
| `POST /api/v1/benchmarks` | Start a run (202). Body: a `BenchmarkConfig`. A cloud model needs `confirm_cloud_usage: true` (422 otherwise) |
| `GET /api/v1/benchmarks/active` | Progress of the running, or most recent, run |
| `POST /api/v1/benchmarks/active/cancel` | Cancel; finished requests are saved |
| `GET /api/v1/benchmarks` | Summaries of saved reports |
| `GET /api/v1/benchmarks/{id}` | Full report |
| `GET /api/v1/benchmarks/{id}/export?format=json\|csv` | Download |
| `PATCH /api/v1/benchmarks/{id}/runs/{index}` | Record a manual score (1 to 5) and notes |

```json
{
  "name": "text baseline",
  "model": {"id": "Qwen3-1.7B-GGUF"},
  "backend": "lemonade",
  "workloads": ["general_qa", "code_generation", "structured_json"],
  "warmup_runs": 1,
  "measured_runs": 3,
  "max_tokens": 256,
  "temperature": 0.0,
  "seed": 42,
  "enable_thinking": false,
  "load_policy": "keep",
  "allow_code_execution": false
}
```

`allow_code_execution` lets the `code_tests` workload run model-written code to score it.
It is off by default and is not a security sandbox. Runs of scored workloads carry `score`,
`score_method`, and `score_detail`; aggregates carry `scored`, `accuracy`, and
`decode_tokens_per_second_median`.

## AMD cloud

Nothing here starts, stops, or resizes a machine. No request can name a URL or a command.

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/cloud/status` | Endpoint configured, loopback, key configured (boolean), SSH host, backend status, one health round trip in ms, served models |
| `GET /api/v1/cloud/gpus` | Device-level `amd-smi` readings. Cached for `interval_seconds`; `sample` is `null` without an SSH host |
| `POST /api/v1/cloud/preflight` | Run the read-only host check over SSH. No body. Returns each check with status, detail, and remediation, plus facts |
| `GET /api/v1/cloud/catalog` | Models whose published facts Antar has verified |
| `POST /api/v1/cloud/feasibility` | Approximate memory budget for a catalog model |
| `GET /api/v1/cloud/cost` | Cost estimate from the operator's session |
| `PUT /api/v1/cloud/cost` | Record price, credit, and instance times. Body: a `CloudSession` |
| `GET /api/v1/cloud/lemonade-provider` | Whether the endpoint is registered with Lemonade's cloud routing |
| `POST /api/v1/cloud/lemonade-provider` | Register it. Body `{"confirm": true}` |
| `DELETE /api/v1/cloud/lemonade-provider` | Remove it |

Feasibility request. Only `model` and `gpu_memory_bytes` are required:

```json
{
  "model": "Qwen/Qwen3-32B",
  "gpu_memory_bytes": 206158430208,
  "gpu_count": 1,
  "max_model_len": 32768,
  "concurrency": 1,
  "gpu_memory_utilization": 0.9,
  "runtime_overhead_bytes_per_gpu": 2147483648
}
```

The response itemizes weights, KV cache, and overhead against usable memory and gives a
`verdict` of `fits`, `tight`, or `does_not_fit`. A model outside the catalog returns 404.

Cost session. Every field is optional; timestamps must include a timezone:

```json
{
  "hourly_price_usd": 4.0,
  "credit_balance_usd": 100.0,
  "instance_started_at": "2026-11-18T10:00:00Z",
  "instance_stopped_at": null
}
```

The estimate returns elapsed seconds, estimated spend, estimated remaining credit and
hours, `running`, and `warnings`. Every value that cannot be computed is `null`. A stop
time is the operator's statement; Antar verifies nothing with a provider.

Registering with Lemonade changes Lemonade's configuration and hands it the endpoint's API
key. It uses the URL in Antar's settings, never one from the request. The provider name is
`antaramd`.

## Comparisons

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/comparisons` | Start a comparison (202) |
| `GET /api/v1/comparisons/active` | Progress of the running, or most recent, comparison |
| `POST /api/v1/comparisons/active/cancel` | Cancel; finished requests are saved |
| `GET /api/v1/comparisons` | Summaries of saved comparisons |
| `GET /api/v1/comparisons/{id}` | Full report |
| `GET /api/v1/comparisons/{id}/export?format=json\|csv\|md` | Download |

```json
{
  "config": {
    "name": "Qwen3 local vs cloud",
    "local": {"backend": "lemonade", "model": {"id": "Qwen3-1.7B-GGUF"}},
    "cloud": {"backend": "amd_cloud", "model": {"id": "Qwen/Qwen3-8B"}},
    "workloads": ["qa_exact", "reasoning_basic"],
    "warmup_runs": 1,
    "measured_runs": 3,
    "max_tokens": 256,
    "temperature": 0.0,
    "seed": 42,
    "enable_thinking": false,
    "allow_code_execution": false,
    "time_budget_minutes": 30
  },
  "confirm_cloud_usage": true
}
```

`confirm_cloud_usage` must be `true`: a comparison keeps a paid instance busy. The local
side must not be a cloud model and the cloud side must not be a local one. A Lemonade
cloud-provider model (`antaramd.<id>` on backend `lemonade`) is accepted as the cloud side.
The two mock models are accepted on either side for offline development, and the report is
then `simulated`. Method and report fields:
[local versus cloud](benchmarks/local-vs-cloud.md).

## Experiments

`GET /api/v1/experiments` lists optimization experiment records. None are produced yet.
