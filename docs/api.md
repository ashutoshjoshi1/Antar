# HTTP API

Base URL `http://localhost:8080`. Interactive reference, generated from the code, is at
`/docs` while the API runs; that is the authority if this page and it disagree.

The API is a local developer tool: no authentication, CORS limited to the configured
dashboard origins. Errors are JSON `{"detail": "..."}`.

| Status | Meaning |
|---|---|
| 404 | Unknown model, benchmark, or run |
| 409 | Model not downloaded, or a benchmark is already running |
| 422 | Invalid request, unsupported image, model without the needed capability |
| 502 | Lemonade was reached but failed the request (for example, out of memory) |
| 503 | Lemonade is not reachable |

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
| `GET /api/v1/models` | Every model from reachable backends: downloaded, loaded, size, quantization, labels |
| `GET /api/v1/models/{backend}/{model_id}` | One model |
| `POST /api/v1/models/load` | Load a downloaded model. Body `{"model": "...", "backend": "lemonade"}` |
| `POST /api/v1/models/unload` | Unload a model |
| `POST /api/v1/models/download` | Start a download. Requires `"confirm": true` |
| `GET /api/v1/models/downloads` | Downloads in progress |

`load` never downloads: a model that is not present returns 409.

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

- `backend` names a configured backend. URLs are not accepted anywhere.
- `images` is optional, user messages only, one per message, PNG, JPEG, or WebP. The
  declared type must match the file's contents. The model must be labelled `vision`.
- Every `settings` field is optional except that `max_tokens` defaults to 512.

Stream events, one JSON object per `data:` line:

```
data: {"type":"delta","content":"Hel","reasoning":""}
data: {"type":"done","result":{"content":"Hello","reasoning":null,"finish_reason":"stop","metrics":{...},"simulated":false}}
data: {"type":"error","message":"...","kind":"BackendRequestError"}
```

A stream ends with exactly one `done` or `error`. Closing the connection cancels
generation in Lemonade.

`metrics` fields are `null` when unavailable: `latency_ms`, `first_chunk_ms` (streaming
only), `prompt_tokens`, `completion_tokens`, `cached_prompt_tokens`,
`prompt_processing_ms`, `generation_ms`, `tokens_per_second`.

## Benchmarks

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/benchmarks/workloads` | Built-in workloads and their prompts |
| `POST /api/v1/benchmarks` | Start a run (202). Body: a `BenchmarkConfig` |
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
  "load_policy": "keep"
}
```

## Experiments

`GET /api/v1/experiments` lists optimization experiment records. None are produced yet.
