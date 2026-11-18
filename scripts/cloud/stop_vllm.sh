#!/usr/bin/env bash
# stop_vllm.sh — stop and remove the vLLM container.
#
# Runs ON THE REMOTE HOST. It stops the model process only. It does not, and
# cannot, stop, resize or destroy the VM.
#
# Source checked 2026-11-18:
#   - https://docs.docker.com/reference/cli/docker/container/stop/ : the
#     timeout option is documented as `-t` / `--timeout` ("Seconds to wait
#     before killing the container"). The page no longer lists `--time`, so the
#     short form is used here.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/cloud/_common.sh
. "${SCRIPT_DIR}/_common.sh"

STOP_TIMEOUT_SECONDS=30

usage() {
  cat <<'EOF'
Usage: stop_vllm.sh [--name NAME]

Gracefully stops (30 s timeout) and removes the vLLM container.

  --name NAME   container name (default: antar-vllm)
  -h, --help    show this help

This stops ONLY the model process. The VM keeps running, and keeps billing,
until you power it off or destroy it in your provider's console.
EOF
}

print_billing_notice() {
  cat <<'EOF'

NOTE: only the model process was affected. The VM is STILL RUNNING and STILL
BILLING. To stop paying, power it off or destroy it in your provider's
console. These scripts never do that for you.
EOF
}

NAME='antar-vllm'

while [ "$#" -gt 0 ]; do
  case "$1" in
    --name) require_value "$@"; NAME="$2"; shift 2 ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

validate_container_name "$NAME"
require_docker

if ! docker container inspect "$NAME" >/dev/null 2>&1; then
  printf 'No container named %s; nothing to stop.\n' "$NAME"
  print_billing_notice
  exit 0
fi

printf 'Stopping %s (up to %s s) ...\n' "$NAME" "$STOP_TIMEOUT_SECONDS"
docker stop -t "$STOP_TIMEOUT_SECONDS" "$NAME" >/dev/null || die "docker stop failed for ${NAME}"
docker rm "$NAME" >/dev/null || die "docker rm failed for ${NAME}"
printf 'Container %s stopped and removed. Downloaded weights were kept.\n' "$NAME"
print_billing_notice
