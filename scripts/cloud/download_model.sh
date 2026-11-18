#!/usr/bin/env bash
# download_model.sh — explicit, confirmed download of model weights into the
# Hugging Face cache, using the Python environment inside the vLLM image.
#
# Runs ON THE REMOTE HOST. Needs no GPU devices and passes none.
#
# Sources checked 2026-11-18:
#   - https://huggingface.co/docs/huggingface_hub/guides/cli : `hf download
#     REPO_ID [--revision REV]` downloads a whole repo into the cache under
#     HF_HOME. That page documents only `hf`; the older `huggingface-cli` name
#     is tried as a fallback and is unverified against current docs.
#   - https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables :
#     HF_TOKEN authenticates; HF_HOME defaults to ~/.cache/huggingface.
#   - https://docs.vllm.ai/en/stable/deployment/docker/ : the cache is mounted
#     at /root/.cache/huggingface in the official docker command.
#   - https://docs.docker.com/reference/cli/docker/container/run/ : `--pull
#     never`; `--env NAME` (no value) forwards NAME from this shell.
# Which CLI the image actually ships is decided at runtime, not assumed.
#
# NOT verified on real AMD hardware by this project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/cloud/_common.sh
. "${SCRIPT_DIR}/_common.sh"

usage() {
  cat <<'EOF'
Usage: download_model.sh --model ORG/NAME --yes [--revision REV] [--image REF]
                         [--model-cache DIR]

Downloads model weights into the Hugging Face cache on this host.

  --model ORG/NAME   Hugging Face model id (required)
  --yes              confirm the download (required; weights can be tens of GB)
  --revision REV     branch, tag or commit hash
  --image REF        image whose Python environment runs the download
                     (default: the pinned vllm/vllm-openai-rocm image; it must
                     already be pulled, this script does not pull it)
  --model-cache DIR  cache directory (default: $HOME/.cache/huggingface)
  -h, --help         show this help

For gated or private models export HF_TOKEN first. It is forwarded to the
container by name and never printed or written to disk by this script.

On success writes ${ANTAR_REMOTE_DIR:-$HOME/antar}/model-download.json:
  {"model","revision","started_at","finished_at","seconds"}
EOF
}

MODEL=''
REVISION=''
IMAGE="$ANTAR_DEFAULT_IMAGE"
MODEL_CACHE="${HOME:-}/.cache/huggingface"
CONFIRMED=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --model) require_value "$@"; MODEL="$2"; shift 2 ;;
    --revision) require_value "$@"; REVISION="$2"; shift 2 ;;
    --image) require_value "$@"; IMAGE="$2"; shift 2 ;;
    --model-cache) require_value "$@"; MODEL_CACHE="$2"; shift 2 ;;
    --yes) CONFIRMED=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

if [ -z "$MODEL" ]; then usage_error "--model ORG/NAME is required"; fi
validate_model_id "$MODEL"
if [ -n "$REVISION" ]; then validate_revision "$REVISION"; fi
validate_image_ref "$IMAGE"
validate_abs_dir_path --model-cache "$MODEL_CACHE"

if [ "$CONFIRMED" -ne 1 ]; then
  printf 'Refusing to download %s without --yes.\n' "$MODEL" >&2
  printf 'Model weights can be tens of GB and take a long time. Check free disk\n' >&2
  printf 'space with check_environment.sh, then re-run with --yes.\n' >&2
  exit 2
fi

require_docker
require_local_image "$IMAGE"

# Create the cache as this user so Docker does not create it as root.
mkdir -p "$MODEL_CACHE" || die "cannot create $MODEL_CACHE"
RECORD_DIR="$(antar_remote_dir)"

DOCKER_ARGS=(
  run --rm
  --pull never
  --entrypoint /bin/sh
  -v "${MODEL_CACHE}:${ANTAR_CONTAINER_HF_HOME}"
)
if [ -n "${HF_TOKEN:-}" ]; then
  # Name only: the value never appears on a command line.
  DOCKER_ARGS+=(--env HF_TOKEN)
  printf 'HF_TOKEN is set and will be forwarded to the container.\n'
else
  printf 'HF_TOKEN is not set: only public models can be downloaded.\n'
fi

# Runs inside the container. Picks whichever Hugging Face CLI the image has.
# shellcheck disable=SC2016  # expanded by the container's sh, not here
IN_CONTAINER='
model="$1"
revision="${2:-}"
if command -v hf >/dev/null 2>&1; then
  set -- hf download "$model"
elif command -v huggingface-cli >/dev/null 2>&1; then
  set -- huggingface-cli download "$model"
else
  echo "error: neither hf nor huggingface-cli is installed in this image" >&2
  exit 127
fi
if [ -n "$revision" ]; then
  set -- "$@" --revision "$revision"
fi
exec "$@"
'

printf 'Downloading %s%s into %s ...\n' "$MODEL" "${REVISION:+ (revision ${REVISION})}" "$MODEL_CACHE"
STARTED_AT="$(utc_now)"
START_EPOCH="$(date +%s)"

if ! docker "${DOCKER_ARGS[@]}" "$IMAGE" -c "$IN_CONTAINER" sh "$MODEL" "$REVISION"; then
  die "download failed; no record written. Partial files may remain in ${MODEL_CACHE}/hub"
fi

FINISHED_AT="$(utc_now)"
SECONDS_TAKEN=$(($(date +%s) - START_EPOCH))

RECORD="${RECORD_DIR}/model-download.json"
write_file_atomic "$RECORD" <<EOF
{
  "model": $(json_string "$MODEL"),
  "revision": $(json_string_or_null "$REVISION"),
  "started_at": $(json_string "$STARTED_AT"),
  "finished_at": $(json_string "$FINISHED_AT"),
  "seconds": ${SECONDS_TAKEN}
}
EOF

printf 'Done in %s s. Record: %s\n' "$SECONDS_TAKEN" "$RECORD"
