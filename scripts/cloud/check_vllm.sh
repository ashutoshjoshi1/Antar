#!/usr/bin/env bash
# check_vllm.sh — probe the vLLM server on 127.0.0.1 and optionally wait for it
# to become ready.
#
# Runs ON THE REMOTE HOST (it also works on the laptop against a tunnel port,
# without --wait's container checks, if you pass the tunnel's --port).
#
# Sources checked 2026-11-18:
#   - https://docs.vllm.ai/en/stable/serving/online_serving/ : /health,
#     /version, /v1/models. /health answers 503 while the model loads.
#   - https://docs.vllm.ai/en/stable/usage/security/ : with an API key set,
#     /v1/* needs `Authorization: Bearer KEY`; /health and /version do not.
#
# NOT verified on real AMD hardware by this project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/cloud/_common.sh
. "${SCRIPT_DIR}/_common.sh"

POLL_INTERVAL_SECONDS=2
HTTP_TIMEOUT_SECONDS=10
LOG_TAIL_LINES=40
MAX_WAIT_SECONDS=86400

usage() {
  cat <<'EOF'
Usage: check_vllm.sh [--port PORT] [--name NAME] [--wait SECONDS]
                     [--api-key-file PATH]

Checks the vLLM server on 127.0.0.1 and prints /version and /v1/models.

  --port PORT          host port (default: 8000)
  --name NAME          container name, used by --wait (default: antar-vllm)
  --wait SECONDS       poll /health every 2 s until it returns 200 or SECONDS
                       pass. Fails at once if the container has exited and
                       prints its last log lines.
  --api-key-file PATH  file (mode 600) holding the API key, for /v1/models
  -h, --help           show this help

With --wait, when the server is seen to become ready, writes
${ANTAR_REMOTE_DIR:-$HOME/antar}/vllm-ready.json:
  {"ready_at","seconds_to_ready","measured_from"}
measured_from is "container_start" (started_at from vllm-deployment.json for
the same container) or "check_start" (when this script started). If the server
is already ready on the first poll, the moment it became ready was not
observed, so no file is written.

Exit status: 0 ready, 1 not ready, 2 bad arguments.
EOF
}

PORT=8000
NAME='antar-vllm'
WAIT=''
API_KEY_FILE=''

while [ "$#" -gt 0 ]; do
  case "$1" in
    --port) require_value "$@"; PORT="$2"; shift 2 ;;
    --name) require_value "$@"; NAME="$2"; shift 2 ;;
    --wait) require_value "$@"; WAIT="$2"; shift 2 ;;
    --api-key-file) require_value "$@"; API_KEY_FILE="$2"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

validate_port --port "$PORT"
validate_container_name "$NAME"
if [ -n "$WAIT" ]; then validate_int --wait "$WAIT" 1 "$MAX_WAIT_SECONDS"; fi
if [ -n "$API_KEY_FILE" ]; then read_api_key_file "$API_KEY_FILE"; fi

if ! command -v curl >/dev/null 2>&1; then
  die "curl is required"
fi

SCRIPT_START_EPOCH="$(date +%s)"
BASE_URL="http://127.0.0.1:${PORT}"

CURL_CONFIG=''
cleanup() {
  if [ -n "$CURL_CONFIG" ]; then rm -f "$CURL_CONFIG"; fi
}
trap cleanup EXIT

# The key goes to curl through a private config file, never the command line.
AUTH_ARGS=()
if [ -n "$API_KEY_FILE" ]; then
  umask 077
  CURL_CONFIG="$(mktemp "${TMPDIR:-/tmp}/antar-curl.XXXXXX")" || die "cannot create a temp file"
  printf 'header = "Authorization: Bearer %s"\n' "$ANTAR_API_KEY" >"$CURL_CONFIG"
  AUTH_ARGS=(--config "$CURL_CONFIG")
fi

health_code() {
  curl -s -o /dev/null -w '%{http_code}' --max-time "$HTTP_TIMEOUT_SECONDS" "${BASE_URL}/health" 2>/dev/null || true
}

container_state() {
  docker container inspect --format '{{.State.Status}}' "$NAME" 2>/dev/null || true
}

print_log_tail() {
  local logs
  logs="$(docker logs --tail "$LOG_TAIL_LINES" "$NAME" 2>&1 || true)"
  printf -- '--- last %s log lines of %s ---\n%s\n--- end of logs ---\n' "$LOG_TAIL_LINES" "$NAME" "$logs" >&2
  if printf '%s' "$logs" | grep -Eqi 'out of memory|OutOfMemory'; then
    cat >&2 <<'EOF'
hint: the logs mention running out of memory. Options: a lower --max-model-len,
a lower --max-num-seqs, a smaller or quantized model, or more GPUs with
--tensor-parallel-size. Check current GPU memory with collect_gpu_metrics.sh.
EOF
  fi
}

# Seconds since the epoch for a UTC timestamp written by start_vllm.sh.
iso_to_epoch() {
  date -u -d "$1" '+%s' 2>/dev/null || date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$1" '+%s' 2>/dev/null
}

# Prints the string value of KEY from a record file these scripts wrote
# (one "key": "value" pair per line).
record_string() {
  sed -n "s/^[[:space:]]*\"$2\":[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" 2>/dev/null | head -n 1 || true
}

write_ready_record() {
  local now_epoch="$1" record_dir deployment started_at start_epoch
  local measured_from='check_start' reference_epoch="$SCRIPT_START_EPOCH"
  local ts_re='^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
  record_dir="$(antar_remote_dir)"
  deployment="${record_dir}/vllm-deployment.json"
  if [ -r "$deployment" ] && [ "$(record_string "$deployment" container_name)" = "$NAME" ]; then
    started_at="$(record_string "$deployment" started_at)"
    if [[ "$started_at" =~ $ts_re ]] && start_epoch="$(iso_to_epoch "$started_at")" &&
      [[ "$start_epoch" =~ ^[0-9]+$ ]] && [ "$start_epoch" -le "$now_epoch" ]; then
      measured_from='container_start'
      reference_epoch="$start_epoch"
    fi
  fi
  write_file_atomic "${record_dir}/vllm-ready.json" <<EOF
{
  "ready_at": $(json_string "$(utc_now)"),
  "seconds_to_ready": $((now_epoch - reference_epoch)),
  "measured_from": $(json_string "$measured_from")
}
EOF
  printf 'Ready after %s s (measured from %s, %s s polling). Record: %s\n' \
    "$((now_epoch - reference_epoch))" "$measured_from" "$POLL_INTERVAL_SECONDS" "${record_dir}/vllm-ready.json"
}

# --- readiness ----------------------------------------------------------------

if [ -n "$WAIT" ]; then
  if ! command -v docker >/dev/null 2>&1; then
    die "--wait needs docker to watch the container"
  fi
  if [ -z "$(container_state)" ]; then
    die "no container named '${NAME}' (or docker is not usable). Start it with start_vllm.sh"
  fi
  deadline=$((SCRIPT_START_EPOCH + WAIT))
  polls=0
  printf 'Waiting up to %s s for %s/health ...\n' "$WAIT" "$BASE_URL"
  while :; do
    code="$(health_code)"
    polls=$((polls + 1))
    if [ "$code" = "200" ]; then break; fi
    state="$(container_state)"
    case "$state" in
      exited | dead | '')
        printf 'error: container %s is not running (state: %s)\n' "$NAME" "${state:-gone}" >&2
        print_log_tail
        exit 1
        ;;
    esac
    if [ "$(date +%s)" -ge "$deadline" ]; then
      printf 'error: not ready after %s s (last /health status: %s, container state: %s)\n' "$WAIT" "$code" "$state" >&2
      print_log_tail
      exit 1
    fi
    sleep "$POLL_INTERVAL_SECONDS"
  done
  if [ "$polls" -eq 1 ]; then
    printf 'Already ready on the first poll: time-to-ready was not observed, vllm-ready.json not written.\n'
  else
    write_ready_record "$(date +%s)"
  fi
else
  code="$(health_code)"
  if [ "$code" != "200" ]; then
    printf 'error: %s/health returned %s (503 while the model loads is normal; 000 means no connection)\n' "$BASE_URL" "$code" >&2
    printf 'Use --wait SECONDS to wait, or look at: docker logs %s\n' "$NAME" >&2
    exit 1
  fi
  printf '%s/health: 200\n' "$BASE_URL"
fi

# --- details ------------------------------------------------------------------

printf '\n/version:\n'
if ! curl -sS --max-time "$HTTP_TIMEOUT_SECONDS" "${BASE_URL}/version"; then
  die "could not read /version"
fi

printf '\n\n/v1/models:\n'
MODELS_BODY="$(mktemp "${TMPDIR:-/tmp}/antar-models.XXXXXX")" || die "cannot create a temp file"
MODELS_CODE="$(curl -sS -o "$MODELS_BODY" -w '%{http_code}' --max-time "$HTTP_TIMEOUT_SECONDS" \
  ${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"} "${BASE_URL}/v1/models" || true)"
cat "$MODELS_BODY"
rm -f "$MODELS_BODY"
printf '\n'
if [ "$MODELS_CODE" = "401" ]; then
  die "/v1/models returned 401: the server has an API key. Pass --api-key-file PATH"
elif [ "$MODELS_CODE" != "200" ]; then
  die "/v1/models returned HTTP ${MODELS_CODE}"
fi
