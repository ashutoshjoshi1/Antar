# Phase 2: AMD cloud inference and local-versus-cloud comparison

> **Status: implemented, awaiting live integration.** Everything on this page exists as
> code with mocked tests. **No request has been sent to a real AMD GPU**, the operator
> scripts have not run on AMD hardware, and there are no benchmark numbers in this
> repository. The [remaining live verification](#remaining-live-verification) lists exactly
> what is still unproven.

## What Phase 2 adds

- **A cloud backend.** `amd_cloud` talks to a self-hosted
  [vLLM](https://docs.vllm.ai/) OpenAI-compatible server on AMD Instinct GPUs, for text chat
  and image understanding, streamed and cancellable. It uses the same chat routes and the
  same result types as Lemonade.
- **Operator scripts** in `scripts/cloud/` to check a host, download weights on request,
  start and stop vLLM in Docker, and open an SSH tunnel. Antar itself never starts or stops
  anything that costs money.
- **Remote checks over SSH**: a read-only preflight and device-level GPU readings from
  `amd-smi`.
- **A memory feasibility estimate** before deployment, from published model facts.
- **A unified model registry**: every model says where it runs (`local`, `cloud`, `mock`),
  who serves it, and how far it is from answering (`configured`, `discovered`,
  `installed`, `loaded`).
- **Reference-answer scoring** for six new workloads: exact match, numeric answers, JSON
  fields, unit-tested code (opt-in), image questions, and text in images.
- **Comparison Lab**: one local model and one cloud model run the same workloads; the
  report lines them up and says who measured each number.
- **Cost controls**: an operator-entered hourly price and credit balance, an estimate from
  elapsed time, a time budget per comparison, and a confirmation before a comparison uses
  cloud time.
- **Lemonade cloud-provider registration** (optional): the same endpoint can be registered
  with Lemonade's own experimental cloud routing.

## Two ways to reach the cloud model

| | Path A: direct adapter | Path B: through Lemonade |
|---|---|---|
| Route | Antar API → SSH tunnel → vLLM | Antar API → Lemonade → provider `antaramd` → SSH tunnel → vLLM |
| Backend name in Antar | `amd_cloud` | `lemonade` (model id `antaramd.<served name>`) |
| Status | Required path. Implemented, mocked tests | Optional. Depends on Lemonade's experimental cloud routing |
| Model facts | From Antar's catalog and configuration | Whatever Lemonade reports |

Both produce the same `ModelSpec`, `ChatResult`, and report types. Details:
[cloud execution architecture](architecture/cloud-execution.md).

## Quick start without a cloud host

Nothing here needs an AMD account, a GPU, or Lemonade.

```bash
uv run antar serve                 # terminal 1
cd apps/web && pnpm dev            # terminal 2
uv run pytest                      # all cloud code runs against stand-in servers
```

- `uv run antar cloud-status` reports `not_configured` and explains what to set.
- `uv run antar cloud-estimate Qwen/Qwen3-32B --gpu-memory-gb 192` prints a memory budget.
- In the dashboard, Comparison Lab accepts the two mock models. The result is labelled
  **Simulated** everywhere, including the exports. It exercises the pipeline and is not a
  measurement.

## Quick start with a real host

You provide the machine. The full procedure is in three pages; this is the outline.

1. **Prepare access and check the host** — [AMD host setup](cloud/amd-setup.md).
   ```bash
   uv run antar cloud-preflight
   ```
2. **Start vLLM on the host** — [ROCm and vLLM](cloud/rocm-vllm.md).
   ```bash
   docker pull vllm/vllm-openai-rocm:v0.34.0-rocm100@sha256:3cb773d23f063afa86291ef75773cdd486154ddea94c213300f4ed7cc42b7af1
   ./download_model.sh --model Qwen/Qwen3-8B --yes
   ./start_vllm.sh --model Qwen/Qwen3-8B --reasoning-parser qwen3 --api-key-file ~/antar/api-key
   ./check_vllm.sh --wait 900 --api-key-file ~/antar/api-key
   ```
3. **Open the tunnel and point Antar at it** — [secure access](cloud/secure-access.md).
   ```bash
   scripts/cloud/start_ssh_tunnel.sh --host my-amd-host
   export ANTAR_CLOUD__BASE_URL=http://127.0.0.1:18000/v1
   export ANTAR_CLOUD__API_KEY=...        # the key in ~/antar/api-key on the host
   uv run antar cloud-status
   ```
4. **Use it.** The cloud model appears on the Models page, in the Playground and Vision
   model selectors, and in Comparison Lab. Methodology:
   [local versus cloud](benchmarks/local-vs-cloud.md).
5. **Shut down.** Follow the [operator checklist](challenge/phase2-demo.md#operator-checklist).

## What is verified, and how

| Area | State |
|---|---|
| vLLM adapter: status, discovery, chat, streaming, images, errors, timeouts, cancellation | Mocked tests against a stand-in server. Not run against vLLM |
| vLLM request and response details | Written from the vLLM documentation, checked 2026-11-18. Several details were not on the pages read; see below |
| Operator scripts | Syntax, argument validation, `--dry-run`, and stub `docker`/`curl`/`amd-smi` on macOS. Never run on AMD hardware |
| Container image `v0.34.0-rocm100` | Tag and digest read from Docker Hub on 2026-11-18. Compatibility with any host driver not verified |
| `amd-smi` parsing | Tested on synthetic documents. AMD documents the commands but not the JSON key names |
| Preflight | Parser tested; the script's Linux and GPU branches cannot run on macOS |
| Memory feasibility | Arithmetic tested. Model facts read from Hugging Face on 2026-11-18. Never compared with a real load |
| Scoring rules | Tested |
| Comparison Lab, exports, cost, time budget, cancellation | Tested end to end against stand-in Lemonade, vLLM, and SSH |
| Lemonade cloud provider (Path B) | **Exercised against a real Lemonade 2026.46.2** on 2026-11-18, with a stand-in server in place of vLLM (below) |
| Model ids | `Qwen/Qwen3-8B`, `Qwen/Qwen3-32B`, `Qwen/Qwen3-VL-8B-Instruct`, `Qwen/Qwen3-VL-32B-Instruct` exist on Hugging Face, Apache-2.0, not gated (2026-11-18) |

### The Path B check

On 2026-11-18, against the real local Lemonade 2026.46.2 and a stand-in OpenAI-compatible
server on loopback — **not vLLM, and no model** — each of these worked:

- provider install (`POST /v1/install` with `backend: cloud`),
- key auth, which required `allow_insecure_http: true` for the `http://` URL,
- model discovery as `antaramd.<id>` with `recipe: cloud`,
- non-streaming chat, streaming chat, and a message with an image content part, each
  relayed correctly through Antar's Lemonade backend.

The provider was then removed. Lemonade labelled the discovered model `vision` on its own;
Antar passes that label through and does not verify it. Path B has not been tested against
real vLLM.

## Remaining live verification

To do once an AMD GPU instance is available and you have authorized its use. Nothing below
has been done.

- [ ] Run the preflight on the real host; fix any branch of `check_environment.sh` that
      misreads it. Record the GPU model, count, memory, driver, and ROCm version it reports.
- [ ] Confirm the image is compatible with the host's amdgpu driver using the
      [ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html);
      change `--image` if it is not.
- [ ] Capture `amd-smi static --json`, `amd-smi metric --json`, and `amd-smi version --json`
      and compare the key names with what `antar/backends/amd_cloud/amd_smi.py` reads. Fix
      the parser and replace the synthetic test documents with the captured shape.
- [ ] Smoke test: download and serve `Qwen/Qwen3-8B`; confirm `/health`, `/version`, and
      `/v1/models`. Confirm the `/v1/models` entry shape (`id`, `root`, `max_model_len`).
- [ ] Confirm the body and status of an authentication failure (Antar treats any 401 or 403
      as one).
- [ ] Real text inference, non-streaming and streaming, with token usage in the final
      stream chunk.
- [ ] Confirm that `chat_template_kwargs: {"enable_thinking": false}` turns reasoning off,
      and that reasoning arrives in `reasoning` with `--reasoning-parser qwen3`.
- [ ] Confirm that closing the stream stops generation on the server.
- [ ] Serve `Qwen/Qwen3-VL-8B-Instruct` with `--vision-images`; run real image inference,
      including two images in one message.
- [ ] Compare the feasibility estimate with the memory actually used after load.
- [ ] Check that `HF_HUB_OFFLINE=1` (set by `start_vllm.sh` unless `--allow-download`) does
      not stop vLLM from loading cached weights.
- [ ] Run a real local-versus-cloud comparison, then serve `Qwen/Qwen3-32B` and repeat.
      Keep the reports; they are the first real results.
- [ ] Register the real endpoint with Lemonade (Path B) and repeat discovery, chat,
      streaming, and vision.
- [ ] `uv run pytest -m amd_live -s`.
- [ ] Update this page, `CLAUDE.md`, and the module docstrings with what was found.

## Known limitations

- vLLM reports token counts but no per-response timings, so every duration for a cloud
  request is measured by the Antar API and includes the tunnel.
- One model per vLLM server. Antar cannot load or unload a cloud model; it reports what is
  being served.
- Requests in a benchmark or comparison run one at a time. Concurrent load is not measured.
- GPU readings are device-level and need an SSH host; without one they are unavailable.
- Download and load times are recorded by the scripts in JSON files on the host
  (`model-download.json`, `vllm-ready.json`). Antar does not read them yet.
- The scored workloads are small, written for this project, and are smoke tests of
  correctness, not a benchmark of model quality.
- Cost figures are arithmetic on numbers you enter. Antar cannot see your bill or your
  instance.
