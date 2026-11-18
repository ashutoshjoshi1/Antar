# AMD host setup

> Not yet run on AMD hardware. See
> [what is verified](../phase2-amd-cloud.md#what-is-verified-and-how).

Antar does not provision anything. You bring a Linux machine with one or more AMD Instinct
GPUs, from whichever provider you use, and Antar checks it and talks to it. Antar never
starts, resizes, stops, or destroys an instance, and never installs or changes a GPU
driver.

## What the host needs

- Linux on x86_64, with the `amdgpu` kernel driver loaded.
- `/dev/kfd` and `/dev/dri` present.
- Docker 23 or newer, usable without `sudo`. (The ROCm 10.0 images use zstd-compressed
  layers.)
- `amd-smi`, for GPU readings. Optional for inference.
- Enough free disk for the model weights. The preflight asks for 100 GB by default.
- SSH access with a key.

A ROCm installation on the host is helpful but not required for inference: the container
carries its own ROCm userspace. The preflight reports a missing host ROCm as a warning.

What your provider gives you — GPU model and count, driver version, storage, a public
address — varies. Do not assume; run the preflight and read what it reports.

## SSH key setup

Keys stay on your machine and outside the repository. Antar never reads a private key: it
runs your own `ssh` with `BatchMode=yes`, so it uses your agent or configuration and never
prompts.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/antar_amd -C "antar"
# Add ~/.ssh/antar_amd.pub to the instance through your provider.
```

An alias in `~/.ssh/config` keeps host details in one place:

```
Host my-amd-host
    HostName 203.0.113.10
    User ubuntu
    IdentityFile ~/.ssh/antar_amd
    IdentitiesOnly yes
```

Check it: `ssh my-amd-host true`.

`.gitignore` excludes `.env`, `configs/antar.yaml`, `*.pem`, `*.key`, `id_rsa*`, and
`id_ed25519*`. Do not weaken it.

## Configure Antar

Two independent settings. Either works without the other.

**The SSH host** (`amd_cloud`) enables the preflight and GPU readings. In
`configs/antar.yaml` (git-ignored):

```yaml
amd_cloud:
  name: my-amd-host
  ssh_host: my-amd-host            # an alias from ~/.ssh/config, a hostname, or an IP
  # ssh_user: ubuntu               # omit when the alias sets it
  # ssh_port: 22
  # ssh_key_path: ~/.ssh/antar_amd # only passed to ssh; omit when the alias sets it
  gpu_poll_interval_seconds: 10    # minimum time between amd-smi samples (2 or more)
```

Or by environment: `ANTAR_AMD_CLOUD__NAME`, `ANTAR_AMD_CLOUD__SSH_HOST`,
`ANTAR_AMD_CLOUD__SSH_USER`, `ANTAR_AMD_CLOUD__SSH_KEY_PATH`,
`ANTAR_AMD_CLOUD__GPU_POLL_INTERVAL_SECONDS`. The values are validated so they cannot be
read as `ssh` options.

**The inference endpoint** (`cloud`) enables cloud inference. It is set after vLLM is
running and the tunnel is open; see [secure access](secure-access.md).

```yaml
cloud:
  base_url: http://127.0.0.1:18000/v1
  vllm_image: vllm/vllm-openai-rocm:v0.34.0-rocm100   # recorded in reports as written
```

The API key goes in the environment, never in YAML: `ANTAR_CLOUD__API_KEY`.

## Run the preflight

The preflight is `scripts/cloud/check_environment.sh`. It is read-only. Three ways to run
it:

```bash
# 1. Through Antar, using the configured SSH host
uv run antar cloud-preflight

# 2. From the dashboard: AMD Cloud page, "Run preflight"

# 3. Directly, without Antar
ssh my-amd-host bash -s -- --machine < scripts/cloud/check_environment.sh
ssh my-amd-host bash -s < scripts/cloud/check_environment.sh      # readable table
```

Options when run directly: `--image REF`, `--model-cache DIR`, `--min-disk-gb N`.

Each check is `pass`, `warn`, `fail`, or `skip`, with a detail and, when it did not pass,
a remediation. `antar cloud-preflight` exits non-zero if any check failed.

| Check | What it looks at |
|---|---|
| `os`, `arch` | Linux, x86_64 |
| `gpu_vendor`, `gpu_model`, `gpu_count`, `gpu_memory` | AMD devices from sysfs and `lspci` |
| `amdgpu_driver` | The kernel module is loaded |
| `rocm_runtime` | A host ROCm install. Warning only: the container has its own |
| `amd_smi` | `amd-smi` is on the PATH |
| `dev_kfd`, `dev_dri` | The device nodes the container needs |
| `docker`, `docker_permissions`, `docker_version` | Docker present, usable without sudo, 23 or newer |
| `disk_space` | Free space on the model cache filesystem |
| `image` | Whether the image is already pulled. Warning only; it is never pulled for you |
| `model_cache` | The Hugging Face cache directory exists and is writable |

It also reports facts it actually read, such as `gpu_model`, `gpu_count`, `gpu_vram_mb`,
`kernel`, `rocm_version`, `amdgpu_version`, and `docker_version`. A fact that could not be
read is absent, not estimated.

## Common errors

| Symptom | Cause | What to do |
|---|---|---|
| `error: no SSH host configured (amd_cloud).` | `amd_cloud` is not set | Add it as above |
| `SSH to the AMD host failed: ...` | `ssh` could not connect or authenticate | Run `ssh <host> true` yourself; fix the key, alias, or network |
| `The AMD host did not answer over SSH within ...` | Host down or unreachable | Check the instance is running; raise `ssh_timeout_seconds` on a slow link |
| `docker_permissions` fails | Your user cannot run Docker without sudo | Add the user to the `docker` group, then log out and in |
| `dev_kfd` or `dev_dri` fails | Driver not loaded, or no GPU passed to the VM | `lsmod \| grep amdgpu`; AMD documents `sudo usermod -aG video,render $USER` for group access |
| `docker_version` fails | Docker older than 23 | Upgrade Docker; the ROCm 10.0 images cannot be pulled otherwise |
| `image` warns | Image not pulled | `docker pull` it yourself; see [ROCm and vLLM](rocm-vllm.md) |
| `scripts/cloud/check_environment.sh was not found` | Antar is not running from a source checkout | Run from the repository |

Antar never fixes these for you, and never uses `sudo`.

## Will the model fit?

Before downloading tens of gigabytes, estimate the memory budget. This is arithmetic on
published model facts, not a measurement.

```bash
uv run antar cloud-estimate Qwen/Qwen3-32B --gpu-memory-gb 192
uv run antar cloud-estimate Qwen/Qwen3-32B --gpu-memory-gb 48 --gpus 2
uv run antar cloud-estimate Qwen/Qwen3-VL-8B-Instruct --gpu-memory-gb 192 \
    --max-model-len 32768 --concurrency 8
```

The same calculator is on the AMD Cloud page and at `POST /api/v1/cloud/feasibility`.

The budget has three parts:

- **Weights**: the size of the model's safetensors files.
- **KV cache**: per token, two tensors per layer of `num_key_value_heads × head_dim`
  values at the weight precision, multiplied by the context length and the number of
  concurrent sequences. This assumes every sequence fills the whole context, the worst
  case.
- **Runtime overhead**: a flat allowance per GPU (2 GiB by default). This is an assumption,
  not a vLLM figure.

It is compared with the GPU memory multiplied by `gpu_memory_utilization` (0.9 by default),
giving `fits`, `tight` (less than 10% headroom), or `does_not_fit`. More than one GPU
assumes `--tensor-parallel-size`; the cost of sharding is not modelled, and neither is the
activation memory of image inputs. Treat `fits` as "worth trying". A real load is the only
proof.

## Model catalog

`antar/models/catalog.py` holds facts read from each model's Hugging Face repository on
2026-11-18. Nothing in it is estimated. A model outside the catalog can still be served;
Antar then knows less about it and says so.

| Model | Modalities | Parameters | Weights | Precision | Max context | Layers | Licence |
|---|---|---|---|---|---|---|---|
| `Qwen/Qwen3-8B` | text | 8,190,735,360 | 16,381,516,776 bytes | BF16 | 40,960 | 36 | Apache-2.0 |
| `Qwen/Qwen3-32B` | text | 32,762,123,264 | 65,524,328,560 bytes | BF16 | 40,960 | 64 | Apache-2.0 |
| `Qwen/Qwen3-VL-8B-Instruct` | text, vision | 8,767,123,696 | 17,534,339,512 bytes | BF16 | 262,144 | 36 | Apache-2.0 |
| `Qwen/Qwen3-VL-32B-Instruct` | text, vision | 33,357,390,064 | 66,714,912,872 bytes | BF16 | 262,144 | 64 | Apache-2.0 |

The catalog also records the commit each row was read from. Pin it with `--revision` when
serving for a reproducible run.

Serve the vision models with a much smaller `--max-model-len` than their 262,144-token
maximum; the KV cache for the full context is very large.

A model outside the catalog is listed with no modality, because vLLM's model list does not
say what a model accepts. To use one for images, declare it:

```yaml
cloud:
  base_url: http://127.0.0.1:18000/v1
  models:
    - id: my-served-name
      source: Org/Model
      modalities: [text, vision]
```

A 70B-class or larger model is possible in principle but is outside the catalog. Check its
licence, its vLLM and ROCm compatibility, and your credit before attempting one.
