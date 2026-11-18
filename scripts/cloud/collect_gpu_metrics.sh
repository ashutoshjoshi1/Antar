#!/usr/bin/env bash
# collect_gpu_metrics.sh — print AMD GPU telemetry as one JSON document per line.
#
# Runs ON THE REMOTE HOST. Read-only.
#
# Source checked 2026-11-18: AMD SMI CLI docs list `amd-smi static --json`,
# `amd-smi metric --json` and `amd-smi version --json`. The JSON key names are
# NOT documented, so this script never looks inside the output: it checks only
# that each output is non-empty, well-formed JSON, strips line breaks (which
# cannot occur inside a JSON string) so a document fits on one line, and embeds
# it otherwise unchanged.
#
# NOT verified on real AMD hardware by this project.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/cloud/_common.sh
. "${SCRIPT_DIR}/_common.sh"

MIN_INTERVAL_SECONDS=2
DEFAULT_INTERVAL_SECONDS=5
COMMAND_TIMEOUT_SECONDS=20

usage() {
  cat <<'EOF'
Usage: collect_gpu_metrics.sh [--count N [--interval SECONDS]]

Prints one JSON document per line on stdout:
  {"collected_at": "...", "static": ..., "metric": ..., "version": ..., "errors": [...]}

static, metric and version hold the output of `amd-smi <name> --json` as
amd-smi printed it, or null when that command failed; each failure adds a
string to errors.

  --count N           emit N documents (default: 1)
  --interval SECONDS  pause between documents (default: 5; minimum 2, smaller
                      values are refused to avoid over-polling the GPUs).
                      Only valid together with --count.
  -h, --help          show this help

Exit status: 0 when every document was printed (even with nulls and errors
inside), 2 for bad arguments.
EOF
}

COUNT=1
INTERVAL=''

while [ "$#" -gt 0 ]; do
  case "$1" in
    --count) require_value "$@"; COUNT="$2"; shift 2 ;;
    --interval) require_value "$@"; INTERVAL="$2"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

validate_int --count "$COUNT" 1 1000000
if [ -n "$INTERVAL" ]; then
  validate_int --interval "$INTERVAL" 0 86400
  if [ "$INTERVAL" -lt "$MIN_INTERVAL_SECONDS" ]; then
    usage_error "--interval must be at least ${MIN_INTERVAL_SECONDS} seconds"
  fi
  if [ "$COUNT" -eq 1 ]; then
    usage_error "--interval only makes sense with --count N (N > 1)"
  fi
else
  INTERVAL="$DEFAULT_INTERVAL_SECONDS"
fi

with_timeout() {
  if command -v timeout >/dev/null 2>&1; then
    timeout "$COMMAND_TIMEOUT_SECONDS" "$@"
  else
    "$@"
  fi
}

# Syntax check only; never inspects keys.
is_json() {
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$1" | python3 -c 'import json, sys; json.load(sys.stdin)' >/dev/null 2>&1
    return
  fi
  local re='^[[:space:]]*(\{.*\}|\[.*\])[[:space:]]*$'
  [[ "$1" =~ $re ]]
}

ERRORS=()
CAPTURED='null'

# capture SUBCOMMAND — sets CAPTURED to the JSON text or null; appends to ERRORS.
capture() {
  local sub="$1" out='' rc=0
  CAPTURED='null'
  if ! command -v amd-smi >/dev/null 2>&1; then
    ERRORS+=("amd-smi ${sub} --json: amd-smi not found on PATH")
    return 0
  fi
  out="$(with_timeout amd-smi "$sub" --json 2>/dev/null)" || rc=$?
  if [ "$rc" -ne 0 ]; then
    ERRORS+=("amd-smi ${sub} --json: exit status ${rc}")
    return 0
  fi
  out="$(printf '%s' "$out" | tr -d '\n\r')"
  if [ -z "$out" ]; then
    ERRORS+=("amd-smi ${sub} --json: empty output")
    return 0
  fi
  if ! is_json "$out"; then
    ERRORS+=("amd-smi ${sub} --json: output is not valid JSON")
    return 0
  fi
  CAPTURED="$out"
}

emit_document() {
  local collected_at static metric version errors_json='' message
  ERRORS=()
  collected_at="$(utc_now)"
  capture static
  static="$CAPTURED"
  capture metric
  metric="$CAPTURED"
  capture version
  version="$CAPTURED"
  for message in ${ERRORS[@]+"${ERRORS[@]}"}; do
    errors_json="${errors_json:+${errors_json}, }$(json_string "$message")"
  done
  printf '{"collected_at": %s, "static": %s, "metric": %s, "version": %s, "errors": [%s]}\n' \
    "$(json_string "$collected_at")" "$static" "$metric" "$version" "$errors_json"
}

emitted=0
while [ "$emitted" -lt "$COUNT" ]; do
  emit_document
  emitted=$((emitted + 1))
  if [ "$emitted" -lt "$COUNT" ]; then sleep "$INTERVAL"; fi
done
