# Cloud operator scripts

Shell scripts for running a self-hosted [vLLM](https://docs.vllm.ai/) OpenAI-compatible
server in Docker on a Linux VM with AMD Instinct GPUs (ROCm), reached from your laptop
through an SSH tunnel.

**Status: not tested on AMD hardware.** They were written against the official docs
(checked 2026-11-18, cited in each script header) and exercised on macOS for syntax,
argument validation, `--dry-run`, and against stub `docker`/`curl`/`amd-smi` commands. The
default image tag has not been verified against any host driver: check it in the
[ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html)
and override with `--image` if needed.

You provide the VM. Nothing here starts, stops, resizes or destroys cloud instances,
installs or changes GPU drivers, uses `sudo`, or pulls a Docker image for you.

## Scripts

| Script | Runs on | What it does |
|---|---|---|
| `check_environment.sh` | remote host | Read-only preflight: OS, GPUs, driver, device nodes, Docker, disk, image, cache. |
| `download_model.sh` | remote host | Explicit weight download into the Hugging Face cache. Refuses without `--yes`. |
| `start_vllm.sh` | remote host | Starts the vLLM container, detached, on `127.0.0.1` only. `--dry-run` prints the command. |
| `check_vllm.sh` | remote host | Probes `/health`, prints `/version` and `/v1/models`; `--wait N` waits for readiness. |
| `stop_vllm.sh` | remote host | Stops and removes the container. **The VM keeps running and billing.** |
| `collect_gpu_metrics.sh` | remote host | Prints `amd-smi` JSON wrapped in one document per line. |
| `start_ssh_tunnel.sh` | laptop | Forwards `127.0.0.1:18000` on the laptop to `127.0.0.1:8000` on the host. |
| `_common.sh` | (sourced) | Shared validation and JSON helpers. Copy it along with the others. |

Every script has `--help`. Exit status `2` means bad arguments.

Typical order:

```bash
# laptop: preflight without copying anything
ssh HOST bash -s -- --machine < scripts/cloud/check_environment.sh

# remote host (after copying scripts/cloud/ there)
docker pull IMAGE                      # your explicit action; see --help for the default
./download_model.sh --model ORG/NAME --yes
./start_vllm.sh --model ORG/NAME --api-key-file ~/antar/api-key
./check_vllm.sh --wait 900 --api-key-file ~/antar/api-key

# laptop
scripts/cloud/start_ssh_tunnel.sh --host HOST

# remote host, when done -- then power off the VM in your provider's console
./stop_vllm.sh
```

## Machine-output contract

Antar's Python side parses these. Treat them as an interface.

`check_environment.sh --machine` prints only tab-separated lines, with no tabs or newlines
inside a field:

```
ANTAR_CHECK<TAB>id<TAB>status<TAB>detail<TAB>remediation
ANTAR_FACT<TAB>key<TAB>value
```

- `status` is `pass`, `warn`, `fail` or `skip`. Exit status is `1` if any check failed.
- Check ids: `os`, `arch`, `gpu_vendor`, `gpu_model`, `gpu_count`, `gpu_memory`,
  `amdgpu_driver`, `rocm_runtime`, `amd_smi`, `dev_kfd`, `dev_dri`, `docker`,
  `docker_permissions`, `docker_version`, `disk_space`, `image`, `model_cache`.
- Fact keys: `os_name`, `os_version`, `kernel`, `arch`, `gpu_count`, `gpu_model`,
  `gpu_vram_mb`, `rocm_version`, `amdgpu_version`, `amd_smi_version`, `docker_version`,
  `disk_free_gb`, `image_present`, `hostname`.
- A fact is printed only when it was read from the host. A missing fact means "not
  available"; nothing is estimated.
- `gpu_count` counts AMD DRM devices from sysfs (so it would include AMD integrated
  graphics). `gpu_vram_mb` is per GPU, in MiB, from `mem_info_vram_total`: one integer when
  all GPUs match, otherwise a comma-separated list in card order. `gpu_model` comes from
  `lspci`; several models are joined with `; `. `amd_smi_version` is the first line of
  `amd-smi version`, unparsed.

JSON records are written to `${ANTAR_REMOTE_DIR:-$HOME/antar}`; unset values are `null`,
timestamps are UTC ISO-8601:

| File | Written by | Keys |
|---|---|---|
| `model-download.json` | `download_model.sh` | `model`, `revision`, `started_at`, `finished_at`, `seconds` |
| `vllm-deployment.json` | `start_vllm.sh` | `container_name`, `image`, `image_digest`, `model`, `served_model_name`, `revision`, `tensor_parallel_size`, `gpu_count`, `max_model_len`, `port`, `weights_cached_at_start`, `started_at` |
| `vllm-ready.json` | `check_vllm.sh --wait` | `ready_at`, `seconds_to_ready`, `measured_from` (`container_start` or `check_start`) |

`vllm-ready.json` is written only when the script watched the server go from not ready to
ready (2 s polling). If the server is already ready on the first poll, no file is written,
because the time it became ready was not observed.

`collect_gpu_metrics.sh` prints, one document per line:

```json
{"collected_at": "...", "static": null, "metric": null, "version": null, "errors": ["..."]}
```

`static`, `metric` and `version` are the output of `amd-smi <name> --json` with line breaks
removed and nothing else changed, or `null` with a string in `errors`. AMD does not document
the key names, so the scripts never read inside that JSON.

## Least privilege

- **Never `--privileged`.** The container gets `/dev/kfd` and `/dev/dri` (or only the
  render nodes named with `--gpus 128,129`).
- **Loopback only.** The port is published as `127.0.0.1:PORT:8000` and there is no option
  to change the bind address. Remote access is the SSH tunnel, also bound to loopback.
- **`--cap-add=SYS_PTRACE` and `--security-opt seccomp=unconfined`** are there because
  they are in the
  [official vLLM ROCm docker command](https://docs.vllm.ai/en/stable/deployment/docker/).
  AMD's ROCm Docker page marks `seccomp=unconfined` as optional: drop it with
  `start_vllm.sh --no-seccomp-unconfined`. Whether vLLM then runs correctly on your host is
  untested here.
- **`--ipc=host`** is also from the official command. Use `--shm-size 16g` (or another
  size) to give the container its own shared memory instead.
- **API key.** `--api-key-file` (mode 600) is passed as `VLLM_API_KEY` through a temporary
  `--env-file` that is deleted after start, so it never appears in `ps`. Anyone who can run
  `docker inspect` on the host can still read it. Per
  [vLLM's security page](https://docs.vllm.ai/en/stable/usage/security/), the key guards
  the `/v1` routes only; `/health`, `/version`, `/metrics`, `/invocations` and others stay
  open, which is one more reason the port is loopback-only. Without a key the server is
  unauthenticated and the script says so loudly.
- **`HF_TOKEN`** is forwarded by name (`--env HF_TOKEN`) and never printed or written.
- **No implicit downloads.** `start_vllm.sh` refuses to start when the model is not in the
  cache and runs with `HF_HUB_OFFLINE=1`, unless you pass `--allow-download`. Images are run
  with `--pull never`.
- **`--env KEY=VALUE`** values are visible in `ps` and `docker inspect`; do not put secrets
  there. Example from AMD's vLLM walkthrough, off by default:
  `--env VLLM_ROCM_USE_AITER_FP4BMM=0` (avoids a warmup segfault on gfx942).
