# Phase 1: local inference and baseline benchmarks

Phase 1 makes Antar do real work on your machine: chat with a local model, ask a
vision-language model about an image, and measure a model with repeatable benchmarks. All
of it runs through [Lemonade](https://lemonade-server.ai) on `localhost`. Nothing is sent
to a cloud service.

## 1. Install Lemonade

Download the installer for your platform from <https://lemonade-server.ai>. On an Apple
Silicon Mac it is a `.pkg`; it installs a background service, so the server starts on its
own.

## 2. Start or connect to the server

Lemonade listens on `http://localhost:13305` by default. Check it:

```bash
curl http://localhost:13305/v1/health
uv run antar backends          # lemonade   available   Connected. ...
```

If your server is elsewhere, or protected by `LEMONADE_API_KEY`, set these before starting
Antar (in the environment or `.env`):

```bash
ANTAR_LEMONADE__BASE_URL=http://localhost:13305/v1    # include /v1
ANTAR_LEMONADE__API_KEY=...                           # only if the server requires one
```

Antar only ever calls the Lemonade URL in its own configuration. The browser never talks
to Lemonade, and no API request can name a URL.

## 3. Download models

**Antar never downloads a model on its own.** Lemonade's own `/load` and chat endpoints
download a missing model implicitly; Antar checks first and refuses instead.

To download one deliberately:

- **Dashboard:** open **Models**, find the model, choose **Download…**, then confirm the
  size shown.
- **Lemonade's own app or CLI** works too; Antar sees the result.

Suggested starting points (sizes are what Lemonade reports):

| Purpose | Model | Download |
|---|---|---|
| Text | `Qwen3-1.7B-GGUF` | about 1 GB |
| Vision | `Qwen3-VL-4B-Instruct-GGUF` | about 3.3 GB |
| Vision, smaller | `Qwen3.5-0.8B-GGUF` or `MiniCPM-V-4.6-GGUF` | under 2 GB |

Any model Lemonade labels `chat` works in the Playground; any model labelled `vision` works
in Vision. The catalog changes between Lemonade releases, so trust the Models page over
this table.

## 4. Start Antar

```bash
uv run antar serve              # API on http://localhost:8080
cd apps/web && pnpm dev         # dashboard on http://localhost:5173
```

## 5. Text inference

Open **Playground**. Pick a model, write a prompt, press Enter.

- The reply streams as it is generated. **Stop generating** cancels it, and Lemonade stops
  working on it.
- Models that reason show their reasoning in a separate, collapsible block. Turn it off
  with **Let the model reason first**. Reasoning counts toward the output limit, so a low
  limit can be used up before any answer appears; Antar says so when that happens. Some
  models reason without Lemonade labelling them as reasoning models.
- The conversation is kept until you choose **New conversation** or change model. It lives
  in the browser tab only.
- **Last response** shows what was measured for that reply, and who measured it.

From the command line:

```bash
curl -N localhost:8080/api/v1/inference/chat/stream -H 'Content-Type: application/json' -d '{
  "model": "Qwen3-1.7B-GGUF",
  "messages": [{"role": "user", "content": "Say hello."}],
  "settings": {"max_tokens": 64, "enable_thinking": false}
}'
```

## 6. Vision inference

Open **Vision**. Choose an image (PNG, JPEG, or WebP, up to 8 MB by default), then ask
about it. Follow-up questions reuse the same image; choosing a different image starts a new
conversation.

The image is held in the browser, sent to the Antar API, and forwarded to your local
Lemonade server. Antar does not write it to disk.

Small vision models are often wrong about text, counts, and fine detail. Treat their
answers as a draft.

## 7. Benchmarks

Open **Benchmarks**, choose a model and one or more workloads, and start.

| Workload | Prompts | Notes |
|---|---|---|
| General question answering | 4 | |
| Code generation | 4 | |
| Structured JSON generation | 3 | Each reply is checked for being parseable JSON |
| Basic image understanding | 3 | Bundled CC0 images; needs a vision model; no score |

Requests run one at a time. Progress is live, and **Cancel** stops the request in flight
and saves what already finished. Defaults are chosen for comparability: temperature 0,
seed 42, reasoning off.

**Model loading** decides what "first request" means:

- *Use the model as it is* loads it only if needed.
- *Reload first* unloads and reloads the model, recording the load time and the first
  request after it separately as a cold start.

## 8. Reading and exporting results

Each run is saved as `data/benchmarks/<id>.json` (git-ignored) and listed under
**Completed runs**. Open one to see:

- **Statistics per workload**: completed requests, error rate, latency mean, median and
  P95, tokens per second mean and median. These cover *measured* requests only.
- **Charts** of latency and generation speed for every measured request.
- **Not measured**: telemetry that was unavailable, with the reason.
- **Responses and manual review**: the model's actual answers, with a 1 to 5 score and
  notes you can record yourself.
- **Compare with**: another run side by side, with a warning listing any difference in
  prompts, settings, or hardware that makes the comparison unfair.

**Export JSON** gives the full report; **Export CSV** gives one row per request. An empty
CSV cell means "not available", never zero.

What the numbers mean:

| Number | Measured by | Includes |
|---|---|---|
| Latency, whole request | Antar API | Transport to Lemonade, prompt processing, generation |
| First chunk | Antar API | Time until the first streamed text arrived |
| Tokens per second | Lemonade, per response | Generation only |
| Prompt processing, generation time | Lemonade, per response | As named |
| Token counts | Lemonade, per response | |
| Waited in the browser (Playground) | Browser | Everything, including the dashboard's own network hop |

See [the benchmark methodology](benchmarks/methodology.md) for the rules behind these.
`examples/benchmarks/illustrative-report.json` shows the file format; it is produced by the
mock backend and is not a result.

## Known limitations

- **Performance only.** There is no quality score for free-text or image answers. JSON
  validity is the one automatic check. Vision answers need a person to judge them.
- **No per-request memory or GPU numbers.** On macOS the model server runs as another user,
  so its memory is not readable, and GPU utilization and power need privileged tools.
  These appear as "unavailable".
- **One image per message.** Lemonade documents image input but not multi-image prompts.
- **Time to first token is not reported per request by Lemonade.** Antar shows the time to
  the first streamed chunk, measured at the API, and labels it as such.
- **One benchmark at a time**, and a benchmark is lost if the API process stops mid-run.
- **Context size and other load options are not exposed.** Models load with Lemonade's own
  defaults.
- **Replies are shown as plain text.** Markdown is not rendered.
- **The API has no authentication.** It is a local developer tool; do not expose it to a
  network.
- **Results are specific** to the machine, Lemonade version, and model file they were
  measured on. Other software running at the same time affects them.
- Text and vision only. Speech, image generation, and video are later phases.
