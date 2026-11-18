# ROCm and vLLM on the AMD host

> Written from the official documentation, checked 2026-11-18. **Not yet run on AMD
> hardware.** Treat every command here as the intended procedure, to be confirmed on your
> host. Report what differs.

The scripts are in `scripts/cloud/`. Copy that directory to the host (including
`_common.sh`); every script has `--help`.

```bash
scp -r scripts/cloud my-amd-host:antar-scripts
ssh my-amd-host
cd antar-scripts
```

## The image

Antar uses the official vLLM ROCm image, `vllm/vllm-openai-rocm`, and not the CUDA image
or any older AMD-published vLLM container.

The scripts default to a pinned tag and digest:

```
vllm/vllm-openai-rocm:v0.34.0-rocm100@sha256:3cb773d23f063afa86291ef75773cdd486154ddea94c213300f4ed7cc42b7af1
```

- Read from Docker Hub on 2026-11-18, when `v0.34.0-rocm100`, `v0.34.0`, and `latest`
  pointed at the same manifest.
- Built on ROCm 10.0, according to the vLLM Docker documentation.
- ROCm 10.0 images use zstd-compressed layers and need Docker 23 or newer.

**Compatibility with your host's amdgpu driver has not been verified by this project.** The
vLLM documentation states no host driver requirement for the ROCm image. Before pulling:

1. Read the host's driver and kernel from the preflight (`amdgpu_version`, `kernel`).
2. Check them against the
   [ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html)
   for the ROCm version the image is built on.
3. If they do not match, choose another tag and pass it with `--image` to every script. The
   legacy `latest-rocm72` tags exist for the older ROCm 7.2 stack but are no longer updated.

Pulling is your explicit action. The scripts run with `--pull never` and refuse if the
image is not present.

```bash
docker pull vllm/vllm-openai-rocm:v0.34.0-rocm100@sha256:3cb773d23f063afa86291ef75773cdd486154ddea94c213300f4ed7cc42b7af1
```

## The container flags, and why

`start_vllm.sh --dry-run` prints the exact `docker run` command without needing Docker.
The flags follow the official vLLM ROCm command:

| Flag | Reason |
|---|---|
| `--device /dev/kfd --device /dev/dri` | The GPU device nodes. `--gpus 128,129` passes only those render nodes instead of all of `/dev/dri` |
| `--group-add=video`, and the host's `render` group by number | Access to the device nodes |
| `--cap-add=SYS_PTRACE`, `--security-opt seccomp=unconfined` | In the official vLLM ROCm command. AMD's ROCm Docker page marks `seccomp=unconfined` as optional; `--no-seccomp-unconfined` drops it. Whether vLLM then works on your host is untested |
| `--ipc=host` | In the official command. `--shm-size 16g` gives the container its own shared memory instead |
| `-p 127.0.0.1:PORT:8000` | Loopback only. There is no option to bind publicly |
| `-v <cache>:/root/.cache/huggingface` | The model cache, so weights survive the container |
| `--pull never` | No implicit image pull |
| `--env HF_HUB_OFFLINE=1` | No implicit weight download, unless `--allow-download` |

Never `--privileged`. The container is not started with `--rm`, so its logs survive a
crash.

## Runbook

### 1. Create an API key

```bash
mkdir -p ~/antar
umask 077
openssl rand -hex 32 > ~/antar/api-key      # mode 600; the scripts refuse a looser file
```

Without `--api-key-file` the server is unauthenticated. It is still loopback-only, and the
script says so loudly, but use a key.

### 2. Download the weights

Explicit and confirmed. Weights are tens of gigabytes; see the sizes in the
[model catalog](amd-setup.md#model-catalog).

```bash
./download_model.sh --model Qwen/Qwen3-8B --yes
```

`--revision REV` pins a commit. For a gated or private model, `export HF_TOKEN=...` first;
it is forwarded by name and never printed. On success the script writes
`~/antar/model-download.json` with the start time, end time, and duration.

### 3. Start the server

Check the estimate first: `uv run antar cloud-estimate <model> --gpu-memory-gb <N>`.

**Connectivity smoke test — Qwen3 8B**

```bash
./start_vllm.sh --model Qwen/Qwen3-8B \
    --reasoning-parser qwen3 \
    --api-key-file ~/antar/api-key
```

**Primary baseline — Qwen3 32B**

```bash
./download_model.sh --model Qwen/Qwen3-32B --yes
./start_vllm.sh --model Qwen/Qwen3-32B \
    --reasoning-parser qwen3 \
    --api-key-file ~/antar/api-key
```

**Vision — Qwen3-VL 8B**

```bash
./download_model.sh --model Qwen/Qwen3-VL-8B-Instruct --yes
./start_vllm.sh --model Qwen/Qwen3-VL-8B-Instruct \
    --max-model-len 32768 \
    --vision-images 4 \
    --api-key-file ~/antar/api-key
```

`--vision-images N` sets how many images one prompt may carry
(`--limit-mm-per-prompt.image N`). Antar sends at most four per message. `--max-model-len`
matters here: the model's maximum is 262,144 tokens, and reserving cache for all of it
wastes memory.

One server serves one model. To change model, stop the container and start another.

**Several GPUs.** Use tensor parallelism only when the model does not fit on one GPU:

```bash
./start_vllm.sh --model Qwen/Qwen3-32B --gpus 128,129 --tensor-parallel-size 2 \
    --api-key-file ~/antar/api-key
```

`--gpus` takes render node numbers (128, 129, …) or paths. The script refuses a
`--tensor-parallel-size` larger than the number of selected GPUs and records the GPU count
it used.

Other options: `--served-model-name`, `--revision`, `--gpu-memory-utilization`,
`--max-num-seqs`, `--port`, `--name`, `--model-cache`, `--env KEY=VALUE`,
`--allow-download`.

On success the script writes `~/antar/vllm-deployment.json`: container name, image and the
image digest actually used, model, served name, revision, tensor-parallel size, GPU count,
context length, port, whether the weights were cached at start, and the start time.

### 4. Wait for it

```bash
./check_vllm.sh --wait 900 --api-key-file ~/antar/api-key
```

This polls `/health` every two seconds; a 503 while the model loads is normal. It prints
`/version` and `/v1/models`, and fails at once with the last log lines if the container
exited. When it sees the server become ready it writes `~/antar/vllm-ready.json` with
`seconds_to_ready`, measured from the container start.

Logs: `docker logs -f antar-vllm`.

### 5. Connect

On your machine, open the tunnel and configure Antar: [secure access](secure-access.md).

### 6. Stop

```bash
./stop_vllm.sh
```

This stops and removes the container. **It stops only the model process.** The machine
keeps running and keeps billing until you power it off or destroy it with your provider.
See the [operator checklist](../challenge/phase2-demo.md#operator-checklist).

## Download time, load time, inference time

Three different things, recorded in three places:

| What | Where |
|---|---|
| Weight download | `model-download.json` on the host (`seconds`) |
| Time until the server is ready | `vllm-ready.json` on the host (`seconds_to_ready`, with `measured_from`) |
| Inference latency | Antar's reports, per request |

`vllm-ready.json` is written only when the script watched the server go from not ready to
ready. If you start with `--allow-download`, the load time includes the download, and
`weights_cached_at_start` in the deployment record says so.

Antar does not read these files yet. Copy them with your results if you want the load and
download times kept with an experiment.

The first inference request after a start is slower. AMD's walkthrough says the first
inference on gfx942 (MI300X, MI325X, MI300A) compiles kernels and takes tens of seconds.
Antar's benchmarks send warm-up requests for this reason and report the first request of a
run separately.

## Common errors

| Symptom | Likely cause | What to do |
|---|---|---|
| `start_vllm.sh` refuses: model not in the cache | No implicit downloads | Run `download_model.sh --yes`, or pass `--allow-download` deliberately |
| `start_vllm.sh` refuses: image not present | No implicit pulls | `docker pull` the image |
| `start_vllm.sh` refuses: a container with that name exists | Earlier run | `./stop_vllm.sh`, or `--name` another |
| Container exits; log mentions out of memory | Model, context, or concurrency too large for the GPU | Lower `--max-model-len` or `--max-num-seqs`, use more GPUs, or serve a smaller model. `check_vllm.sh --wait` prints a hint |
| Antar reports `GPU memory exhausted on the cloud host` | An out-of-memory error during a request | Same as above |
| `/health` stays 503 | Still loading, or stuck | Watch `docker logs -f antar-vllm` |
| Segfault during warm-up on gfx942 | Known issue per AMD's walkthrough | `--env VLLM_ROCM_USE_AITER_FP4BMM=0` |
| Permission denied on `/dev/kfd` | Group membership | See the preflight remediation for `dev_kfd` |
| Antar: `The cloud endpoint rejected the request (401)` | Key mismatch | `ANTAR_CLOUD__API_KEY` must equal the contents of the key file |
| Antar: `'<model>' is not known to accept images` | A vision model outside the catalog | Declare it under `cloud.models`; see [setup](amd-setup.md#model-catalog) |

## What is verified, and what is from documentation

Verified in the vLLM CLI reference (2026-11-18): `--model`, `--served-model-name`,
`--revision`, `--tensor-parallel-size`, `--gpu-memory-utilization`, `--max-model-len`,
`--max-num-seqs`, `--reasoning-parser`, `--limit-mm-per-prompt`. `VLLM_API_KEY` is on
vLLM's security page.

From documentation but not confirmed by running: the dot form
`--limit-mm-per-prompt.image N` (shown in the multimodal inputs page), the `qwen3`
reasoning parser value (shown in the reasoning outputs page), the effect of
`HF_HUB_OFFLINE=1` on vLLM, and the `hf download` command inside the image.

Not verified at all: that this image runs on any particular host, that any of these models
load under it, and any performance figure. There are none in this repository.

Sources: [vLLM Docker deployment](https://docs.vllm.ai/en/stable/deployment/docker/),
[vLLM security](https://docs.vllm.ai/en/stable/usage/security/),
[Serving LLMs on Instinct](https://rocm.docs.amd.com/projects/amd-skills/en/latest/walkthroughs/serving-llms-on-instinct.html),
[ROCm documentation](https://rocm.docs.amd.com/).
