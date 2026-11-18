#!/usr/bin/env bash
# start_vllm.sh — start the vLLM OpenAI-compatible server in Docker, detached,
# published on 127.0.0.1 only.
#
# Runs ON THE REMOTE HOST. Reach the port from your laptop with
# start_ssh_tunnel.sh. There is deliberately no option to bind publicly.
#
# Sources checked 2026-11-18:
#   - https://docs.vllm.ai/en/stable/deployment/docker/ : official ROCm command
#       docker run --rm --group-add=video --cap-add=SYS_PTRACE
#         --security-opt seccomp=unconfined --device /dev/kfd --device /dev/dri
#         -v ~/.cache/huggingface:/root/.cache/huggingface
#         --env "HF_TOKEN=$HF_TOKEN" -p 8000:8000 --ipc=host
#         vllm/vllm-openai-rocm:<tag> --model <id>
#     and "use the ipc=host flag or --shm-size flag" for shared memory.
#     Differences here, all on purpose: no --rm (logs survive a crash), -d,
#     loopback-only publish, HF_TOKEN forwarded by name, never --privileged.
#   - AMD's vLLM walkthrough also adds the render group, and passes single GPUs
#     as `--device /dev/kfd --device /dev/dri/renderD128`. AMD's ROCm docker
#     page marks seccomp=unconfined as optional (--no-seccomp-unconfined).
#     AMD's walkthrough env VLLM_ROCM_USE_AITER_FP4BMM=0 (avoids a warmup
#     segfault on gfx942) is not set by default: use --env if you need it.
#   - https://docs.vllm.ai/en/stable/cli/serve/ : --model, --served-model-name,
#     --revision, --tensor-parallel-size, --gpu-memory-utilization,
#     --max-model-len, --max-num-seqs, --reasoning-parser, --limit-mm-per-prompt
#     are all listed. The dot form `--limit-mm-per-prompt.image N` and the
#     `qwen3` reasoning parser value come from the same day's doc check that
#     produced this script's brief; the page fetch made while writing the
#     script confirmed the flags but did not show those two details.
#     --host/--port/--api-key are listed too but not used: the container keeps
#     vLLM's default port and the key goes through the environment.
#   - https://docs.vllm.ai/en/stable/usage/security/ : "The --api-key flag (or
#     VLLM_API_KEY environment variable) provides authentication". The key only
#     guards /v1 (and /v2, /inference, /cohere) routes; /health, /version,
#     /metrics, /invocations and others stay open. Hence loopback-only.
#   - https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables :
#     HF_HUB_OFFLINE=1 means "no HTTP calls will be made to the Hugging Face
#     Hub". Set here unless --allow-download is given.
#   - https://docs.docker.com/reference/cli/docker/container/run/ : --pull
#     never, --env-file, `--env NAME` forwarding, -p 127.0.0.1:HOST:CONTAINER.
#
# NOT verified on real AMD hardware by this project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/cloud/_common.sh
. "${SCRIPT_DIR}/_common.sh"

FIRST_RENDER_NODE=128
AMD_PCI_VENDOR='0x1002'
# Set by this script; --env may not override them.
RESERVED_ENV_KEYS=' HF_TOKEN VLLM_API_KEY HF_HUB_OFFLINE '

usage() {
  cat <<'EOF'
Usage: start_vllm.sh --model ORG/NAME [options]

Starts vLLM in a detached Docker container, published on 127.0.0.1 only.

Required:
  --model ORG/NAME            Hugging Face model id

Model and server:
  --served-model-name NAME    name clients use in the API
  --revision REV              branch, tag or commit hash
  --max-model-len N           context length
  --gpu-memory-utilization F  fraction of GPU memory, 0 < F <= 1
  --max-num-seqs N            sequences per iteration
  --tensor-parallel-size N    passed only when N > 1; N must not exceed the
                              number of selected GPUs
  --vision-images N           adds --limit-mm-per-prompt.image N
  --reasoning-parser NAME     e.g. qwen3

Container:
  --image REF                 default: the pinned vllm/vllm-openai-rocm image
                              (must already be pulled; never pulled here)
  --name NAME                 container name (default: antar-vllm)
  --port PORT                 host port on 127.0.0.1 (default: 8000)
  --model-cache DIR           default: $HOME/.cache/huggingface
  --gpus LIST                 comma-separated render nodes, e.g. 128,129 or
                              /dev/dri/renderD128 (default: all of /dev/dri)
  --shm-size SIZE             e.g. 16g; used instead of the default --ipc=host
  --no-seccomp-unconfined     drop --security-opt seccomp=unconfined
  --env KEY=VALUE             extra container env, repeatable. Not for
                              secrets: the value is visible in `ps`.

Safety:
  --api-key-file PATH         file (mode 600) holding the API key. Without it
                              the server is unauthenticated (loopback only).
  --allow-download            let vLLM download missing weights. Without it
                              the script refuses when the model is not cached
                              and runs the container with HF_HUB_OFFLINE=1.
  --dry-run                   print the docker command (secrets redacted) and
                              exit. Needs no docker and changes nothing.
  -h, --help                  show this help

HF_TOKEN, when exported, is forwarded to the container by name.

Writes ${ANTAR_REMOTE_DIR:-$HOME/antar}/vllm-deployment.json on success.
EOF
}

MODEL=''
SERVED_MODEL_NAME=''
REVISION=''
IMAGE="$ANTAR_DEFAULT_IMAGE"
NAME='antar-vllm'
PORT=8000
MODEL_CACHE="${HOME:-}/.cache/huggingface"
TENSOR_PARALLEL_SIZE=''
GPUS=''
MAX_MODEL_LEN=''
GPU_MEMORY_UTILIZATION=''
MAX_NUM_SEQS=''
VISION_IMAGES=''
REASONING_PARSER=''
SHM_SIZE=''
SECCOMP_UNCONFINED=1
EXTRA_ENV=()
API_KEY_FILE=''
ALLOW_DOWNLOAD=0
DRY_RUN=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --model) require_value "$@"; MODEL="$2"; shift 2 ;;
    --served-model-name) require_value "$@"; SERVED_MODEL_NAME="$2"; shift 2 ;;
    --revision) require_value "$@"; REVISION="$2"; shift 2 ;;
    --image) require_value "$@"; IMAGE="$2"; shift 2 ;;
    --name) require_value "$@"; NAME="$2"; shift 2 ;;
    --port) require_value "$@"; PORT="$2"; shift 2 ;;
    --model-cache) require_value "$@"; MODEL_CACHE="$2"; shift 2 ;;
    --tensor-parallel-size) require_value "$@"; TENSOR_PARALLEL_SIZE="$2"; shift 2 ;;
    --gpus) require_value "$@"; GPUS="$2"; shift 2 ;;
    --max-model-len) require_value "$@"; MAX_MODEL_LEN="$2"; shift 2 ;;
    --gpu-memory-utilization) require_value "$@"; GPU_MEMORY_UTILIZATION="$2"; shift 2 ;;
    --max-num-seqs) require_value "$@"; MAX_NUM_SEQS="$2"; shift 2 ;;
    --vision-images) require_value "$@"; VISION_IMAGES="$2"; shift 2 ;;
    --reasoning-parser) require_value "$@"; REASONING_PARSER="$2"; shift 2 ;;
    --shm-size) require_value "$@"; SHM_SIZE="$2"; shift 2 ;;
    --env) require_value "$@"; EXTRA_ENV+=("$2"); shift 2 ;;
    --api-key-file) require_value "$@"; API_KEY_FILE="$2"; shift 2 ;;
    --no-seccomp-unconfined) SECCOMP_UNCONFINED=0; shift ;;
    --allow-download) ALLOW_DOWNLOAD=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

# --- validation ---------------------------------------------------------------

if [ -z "$MODEL" ]; then usage_error "--model ORG/NAME is required"; fi
validate_model_id "$MODEL"
if [ -n "$REVISION" ]; then validate_revision "$REVISION"; fi
validate_image_ref "$IMAGE"
validate_container_name "$NAME"
validate_port --port "$PORT"
validate_abs_dir_path --model-cache "$MODEL_CACHE"

if [ -n "$SERVED_MODEL_NAME" ]; then
  SERVED_RE='^[A-Za-z0-9][A-Za-z0-9._/:-]{0,199}$'
  if ! [[ "$SERVED_MODEL_NAME" =~ $SERVED_RE ]]; then
    usage_error "--served-model-name must match [A-Za-z0-9][A-Za-z0-9._/:-]*"
  fi
fi
if [ -n "$TENSOR_PARALLEL_SIZE" ]; then validate_int --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" 1 64; fi
if [ -n "$MAX_MODEL_LEN" ]; then validate_int --max-model-len "$MAX_MODEL_LEN" 1 100000000; fi
if [ -n "$MAX_NUM_SEQS" ]; then validate_int --max-num-seqs "$MAX_NUM_SEQS" 1 100000; fi
if [ -n "$VISION_IMAGES" ]; then validate_int --vision-images "$VISION_IMAGES" 0 1000; fi
if [ -n "$GPU_MEMORY_UTILIZATION" ]; then
  FRACTION_RE='^(0\.[0-9]*[1-9][0-9]*|1(\.0+)?)$'
  if ! [[ "$GPU_MEMORY_UTILIZATION" =~ $FRACTION_RE ]]; then
    usage_error "--gpu-memory-utilization must be a fraction with 0 < F <= 1, e.g. 0.9"
  fi
fi
if [ -n "$REASONING_PARSER" ]; then
  PARSER_RE='^[A-Za-z0-9_-]{1,64}$'
  if ! [[ "$REASONING_PARSER" =~ $PARSER_RE ]]; then
    usage_error "--reasoning-parser must match [A-Za-z0-9_-]+"
  fi
fi
if [ -n "$SHM_SIZE" ]; then
  SHM_RE='^[1-9][0-9]{0,11}[bkmgBKMG]?$'
  if ! [[ "$SHM_SIZE" =~ $SHM_RE ]]; then
    usage_error "--shm-size must be a size such as 16g or 8192m"
  fi
fi

ENV_RE='^([A-Za-z_][A-Za-z0-9_]*)=([^[:cntrl:]]*)$'
for pair in ${EXTRA_ENV[@]+"${EXTRA_ENV[@]}"}; do
  if ! [[ "$pair" =~ $ENV_RE ]]; then
    usage_error "--env expects KEY=VALUE with KEY matching [A-Za-z_][A-Za-z0-9_]*"
  fi
  case "$RESERVED_ENV_KEYS" in
    *" ${BASH_REMATCH[1]} "*)
      usage_error "--env ${BASH_REMATCH[1]} is managed by this script (export HF_TOKEN, --api-key-file, --allow-download)"
      ;;
  esac
done

# --gpus: render node numbers (128, 129, ...) or /dev/dri/renderDNNN paths.
GPU_DEVICES=()
if [ -n "$GPUS" ]; then
  LIST_RE='^[^,]+(,[^,]+)*$'
  ITEM_RE='^(/dev/dri/renderD)?([0-9]{1,4})$'
  if ! [[ "$GPUS" =~ $LIST_RE ]]; then
    usage_error "--gpus must be a comma-separated list with no empty entries"
  fi
  IFS=',' read -r -a GPU_ITEMS <<<"$GPUS"
  for item in "${GPU_ITEMS[@]}"; do
    if ! [[ "$item" =~ $ITEM_RE ]]; then
      usage_error "--gpus entry '${item}' must be a render node number or /dev/dri/renderDNNN"
    fi
    node_number="${BASH_REMATCH[2]}"
    if [ "$((10#$node_number))" -lt "$FIRST_RENDER_NODE" ]; then
      usage_error "--gpus entry '${item}': render nodes are numbered from ${FIRST_RENDER_NODE} (see: ls /dev/dri)"
    fi
    device="/dev/dri/renderD$((10#$node_number))"
    for seen in ${GPU_DEVICES[@]+"${GPU_DEVICES[@]}"}; do
      if [ "$seen" = "$device" ]; then usage_error "--gpus lists ${device} twice"; fi
    done
    GPU_DEVICES+=("$device")
  done
fi

# How many GPUs the container will see. Empty means "could not determine".
GPU_COUNT=''
if [ "${#GPU_DEVICES[@]}" -gt 0 ]; then
  GPU_COUNT="${#GPU_DEVICES[@]}"
else
  amd_nodes=0
  for node in /sys/class/drm/renderD*; do
    if [ -r "${node}/device/vendor" ] && [ "$(cat "${node}/device/vendor" 2>/dev/null || true)" = "$AMD_PCI_VENDOR" ]; then
      amd_nodes=$((amd_nodes + 1))
    fi
  done
  if [ "$amd_nodes" -gt 0 ]; then GPU_COUNT="$amd_nodes"; fi
fi

if [ -n "$TENSOR_PARALLEL_SIZE" ] && [ "$TENSOR_PARALLEL_SIZE" -gt 1 ]; then
  if [ -n "$GPU_COUNT" ]; then
    if [ "$TENSOR_PARALLEL_SIZE" -gt "$GPU_COUNT" ]; then
      usage_error "--tensor-parallel-size ${TENSOR_PARALLEL_SIZE} exceeds the ${GPU_COUNT} selected GPU(s)"
    fi
  elif [ "$DRY_RUN" -eq 0 ]; then
    die "cannot count AMD GPUs on this host to validate --tensor-parallel-size; select them with --gpus"
  fi
fi

if [ -n "$API_KEY_FILE" ]; then
  read_api_key_file "$API_KEY_FILE"
fi

# --- host state (skipped by --dry-run, which must work without docker) --------

CACHED_MODEL_DIR="${MODEL_CACHE}/hub/models--${MODEL//\//--}"
WEIGHTS_CACHED=false
if [ -d "$CACHED_MODEL_DIR" ]; then WEIGHTS_CACHED=true; fi

if [ "$DRY_RUN" -eq 0 ]; then
  require_docker
  if docker container inspect "$NAME" >/dev/null 2>&1; then
    die "a container named '${NAME}' already exists. Stop it with stop_vllm.sh --name ${NAME}, or pick another --name"
  fi
  require_local_image "$IMAGE"
  if [ ! -c /dev/kfd ]; then die "/dev/kfd is missing (run check_environment.sh)"; fi
  if [ ! -d /dev/dri ]; then die "/dev/dri is missing (run check_environment.sh)"; fi
  for device in ${GPU_DEVICES[@]+"${GPU_DEVICES[@]}"}; do
    if [ ! -c "$device" ]; then die "${device} does not exist (see: ls /dev/dri)"; fi
  done
  if [ "$WEIGHTS_CACHED" = false ] && [ "$ALLOW_DOWNLOAD" -eq 0 ]; then
    die "weights for ${MODEL} are not in ${MODEL_CACHE} (no ${CACHED_MODEL_DIR}). Download them explicitly with download_model.sh --model ${MODEL} --yes, or pass --allow-download"
  fi
  # Create the cache as this user so Docker does not create it as root.
  mkdir -p "$MODEL_CACHE" || die "cannot create $MODEL_CACHE"
fi

# --- docker command -----------------------------------------------------------

# Everything before the image. No secret value is ever placed in this array.
RUN_HEAD=(run -d --pull never --name "$NAME" --group-add=video)

# AMD's walkthrough adds the render group. Use the host's numeric GID: device
# nodes carry host GIDs, and a group *name* fails if the image does not define it.
if command -v getent >/dev/null 2>&1; then
  RENDER_GID="$(getent group render 2>/dev/null | cut -d: -f3 || true)"
  if [[ "$RENDER_GID" =~ ^[0-9]+$ ]]; then
    RUN_HEAD+=(--group-add "$RENDER_GID")
  fi
fi

RUN_HEAD+=(--cap-add=SYS_PTRACE)
if [ "$SECCOMP_UNCONFINED" -eq 1 ]; then
  RUN_HEAD+=(--security-opt seccomp=unconfined)
fi

RUN_HEAD+=(--device /dev/kfd)
if [ "${#GPU_DEVICES[@]}" -gt 0 ]; then
  for device in "${GPU_DEVICES[@]}"; do
    RUN_HEAD+=(--device "$device")
  done
else
  RUN_HEAD+=(--device /dev/dri)
fi

RUN_HEAD+=(-v "${MODEL_CACHE}:${ANTAR_CONTAINER_HF_HOME}")
# Loopback only. Do not add a way to change the bind address.
RUN_HEAD+=(-p "127.0.0.1:${PORT}:${ANTAR_CONTAINER_PORT}")

if [ -n "$SHM_SIZE" ]; then
  RUN_HEAD+=(--shm-size "$SHM_SIZE")
else
  RUN_HEAD+=(--ipc=host)
fi

if [ -n "${HF_TOKEN:-}" ]; then
  RUN_HEAD+=(--env HF_TOKEN)
fi
if [ "$ALLOW_DOWNLOAD" -eq 0 ]; then
  RUN_HEAD+=(--env HF_HUB_OFFLINE=1)
fi
for pair in ${EXTRA_ENV[@]+"${EXTRA_ENV[@]}"}; do
  RUN_HEAD+=(--env "$pair")
done

# The image and the arguments passed to vLLM.
RUN_TAIL=("$IMAGE" --model "$MODEL")
if [ -n "$SERVED_MODEL_NAME" ]; then RUN_TAIL+=(--served-model-name "$SERVED_MODEL_NAME"); fi
if [ -n "$REVISION" ]; then RUN_TAIL+=(--revision "$REVISION"); fi
if [ -n "$TENSOR_PARALLEL_SIZE" ] && [ "$TENSOR_PARALLEL_SIZE" -gt 1 ]; then
  RUN_TAIL+=(--tensor-parallel-size "$TENSOR_PARALLEL_SIZE")
fi
if [ -n "$MAX_MODEL_LEN" ]; then RUN_TAIL+=(--max-model-len "$MAX_MODEL_LEN"); fi
if [ -n "$GPU_MEMORY_UTILIZATION" ]; then RUN_TAIL+=(--gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"); fi
if [ -n "$MAX_NUM_SEQS" ]; then RUN_TAIL+=(--max-num-seqs "$MAX_NUM_SEQS"); fi
if [ -n "$VISION_IMAGES" ]; then RUN_TAIL+=(--limit-mm-per-prompt.image "$VISION_IMAGES"); fi
if [ -n "$REASONING_PARSER" ]; then RUN_TAIL+=(--reasoning-parser "$REASONING_PARSER"); fi

print_command() {
  printf 'docker'
  printf ' %q' "${RUN_HEAD[@]}"
  if [ -n "$API_KEY_FILE" ]; then
    printf ' --env-file <REDACTED: temp file holding VLLM_API_KEY>'
  fi
  printf ' %q' "${RUN_TAIL[@]}"
  printf '\n'
}

warn_unauthenticated() {
  cat >&2 <<EOF
############################################################################
# WARNING: no --api-key-file given. The server will be UNAUTHENTICATED.
# It is published on 127.0.0.1:${PORT} only, so it is reachable just from this
# host and through your SSH tunnel -- but by every local user of this host.
############################################################################
EOF
}

if [ "$DRY_RUN" -eq 1 ]; then
  printf '# dry run: nothing was started; docker, devices and the weight cache were not checked\n'
  if [ -z "$GPU_COUNT" ]; then
    printf '# dry run: AMD GPUs could not be counted on this machine\n'
  fi
  print_command
  if [ -z "$API_KEY_FILE" ]; then warn_unauthenticated; fi
  exit 0
fi

ENV_FILE=''
cleanup() {
  if [ -n "$ENV_FILE" ]; then rm -f "$ENV_FILE"; fi
}
trap cleanup EXIT

ENV_FILE_ARGS=()
if [ -n "$API_KEY_FILE" ]; then
  umask 077
  ENV_FILE="$(mktemp "${TMPDIR:-/tmp}/antar-vllm-env.XXXXXX")" || die "cannot create a temp env file"
  # printf is a shell builtin: the key never appears in a process list.
  printf 'VLLM_API_KEY=%s\n' "$ANTAR_API_KEY" >"$ENV_FILE"
  ENV_FILE_ARGS=(--env-file "$ENV_FILE")
else
  warn_unauthenticated
fi

RECORD_DIR="$(antar_remote_dir)"

printf 'Starting container %s:\n' "$NAME"
print_command
if ! docker "${RUN_HEAD[@]}" ${ENV_FILE_ARGS[@]+"${ENV_FILE_ARGS[@]}"} "${RUN_TAIL[@]}"; then
  die "docker run failed. If a container was created, inspect it with: docker logs ${NAME}"
fi
STARTED_AT="$(utc_now)"
cleanup
ENV_FILE=''

# The digest of the image actually used. Empty (null) for images with no
# registry digest, e.g. ones built locally.
IMAGE_DIGEST="$(docker image inspect --format '{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null || true)"
DIGEST_RE='^[A-Za-z0-9._/:-]+@sha256:[0-9a-f]{64}$'
if ! [[ "$IMAGE_DIGEST" =~ $DIGEST_RE ]]; then
  warn "could not read a registry digest for ${IMAGE}; recording null"
  IMAGE_DIGEST=''
fi

RECORD="${RECORD_DIR}/vllm-deployment.json"
write_file_atomic "$RECORD" <<EOF
{
  "container_name": $(json_string "$NAME"),
  "image": $(json_string "$IMAGE"),
  "image_digest": $(json_string_or_null "$IMAGE_DIGEST"),
  "model": $(json_string "$MODEL"),
  "served_model_name": $(json_string_or_null "$SERVED_MODEL_NAME"),
  "revision": $(json_string_or_null "$REVISION"),
  "tensor_parallel_size": $(json_raw_or_null "$TENSOR_PARALLEL_SIZE"),
  "gpu_count": $(json_raw_or_null "$GPU_COUNT"),
  "max_model_len": $(json_raw_or_null "$MAX_MODEL_LEN"),
  "port": ${PORT},
  "weights_cached_at_start": ${WEIGHTS_CACHED},
  "started_at": $(json_string "$STARTED_AT")
}
EOF

cat <<EOF

Container started. Record: ${RECORD}
The model is still loading; /health returns 503 until it is ready.

  Wait for readiness:  ${SCRIPT_DIR}/check_vllm.sh --name ${NAME} --port ${PORT} --wait 900
  Follow the logs:     docker logs -f ${NAME}
  Stop the server:     ${SCRIPT_DIR}/stop_vllm.sh --name ${NAME}

The container is not removed when it exits, so logs survive a crash.
The first request can be slow while GPU kernels compile (AMD's walkthrough
reports about 40-45 s on gfx942).
EOF
