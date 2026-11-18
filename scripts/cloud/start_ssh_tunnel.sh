#!/usr/bin/env bash
# start_ssh_tunnel.sh — forward a loopback port on the LAPTOP to the vLLM
# server's loopback port on the remote host.
#
# Runs ON THE LAPTOP (the only script here that does). Self-contained; works
# with the bash 3.2 that macOS ships.
#
# Both ends are bound to 127.0.0.1 explicitly, so the model server is never
# exposed on a network interface of either machine. Uses only standard OpenSSH
# client options (-N, -L, -f, -i, ExitOnForwardFailure, ServerAliveInterval,
# ServerAliveCountMax, IdentitiesOnly; see `man ssh` and `man ssh_config`).
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: start_ssh_tunnel.sh --host SSH_TARGET [--local-port PORT]
                           [--remote-port PORT] [--identity PATH]
                           [--background] [--dry-run]

Opens: 127.0.0.1:LOCAL (laptop) -> 127.0.0.1:REMOTE (remote host)

  --host SSH_TARGET   ssh config alias, or user@host (required). For IPv6 or
                      anything unusual, define an alias in ~/.ssh/config.
  --local-port PORT   laptop port (default: 18000)
  --remote-port PORT  vLLM port on the remote host (default: 8000)
  --identity PATH     private key file to use. It is passed to ssh by path
                      only; never read, copied or printed by this script.
  --background        detach after the forward is up (ssh -f)
  --dry-run           print the ssh command and exit without connecting
  -h, --help          show this help

Then point Antar at the tunnel:
  ANTAR_CLOUD__BASE_URL=http://127.0.0.1:LOCAL/v1
EOF
}

usage_error() {
  printf 'error: %s\n(run with --help for usage)\n' "$*" >&2
  exit 2
}

require_value() {
  if [ "$#" -lt 2 ]; then
    usage_error "$1 requires a value"
  fi
}

validate_port() {
  local re='^[1-9][0-9]{0,4}$'
  if ! [[ "$2" =~ $re ]] || [ "$2" -gt 65535 ]; then
    usage_error "$1 must be a port between 1 and 65535"
  fi
}

HOST=''
LOCAL_PORT=18000
REMOTE_PORT=8000
IDENTITY=''
BACKGROUND=0
DRY_RUN=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) require_value "$@"; HOST="$2"; shift 2 ;;
    --local-port) require_value "$@"; LOCAL_PORT="$2"; shift 2 ;;
    --remote-port) require_value "$@"; REMOTE_PORT="$2"; shift 2 ;;
    --identity) require_value "$@"; IDENTITY="$2"; shift 2 ;;
    --background) BACKGROUND=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

if [ -z "$HOST" ]; then usage_error "--host SSH_TARGET is required"; fi
# Conservative: [user@]host, neither part may start with '-', no spaces, no
# option-like or shell-special characters.
HOST_RE='^([A-Za-z0-9_][A-Za-z0-9._-]{0,63}@)?[A-Za-z0-9][A-Za-z0-9._-]{0,252}$'
if ! [[ "$HOST" =~ $HOST_RE ]]; then
  usage_error "--host must be an ssh config alias or user@host ([A-Za-z0-9._-] only, not starting with '-')"
fi
validate_port --local-port "$LOCAL_PORT"
validate_port --remote-port "$REMOTE_PORT"
if [ -n "$IDENTITY" ]; then
  case "$IDENTITY" in
    -*) usage_error "--identity must be a file path" ;;
  esac
  if [ ! -f "$IDENTITY" ] || [ ! -r "$IDENTITY" ]; then
    usage_error "--identity: ${IDENTITY} is not a readable file"
  fi
fi

if ! command -v ssh >/dev/null 2>&1; then
  printf 'error: ssh is not installed\n' >&2
  exit 1
fi

FORWARD="127.0.0.1:${LOCAL_PORT}:127.0.0.1:${REMOTE_PORT}"
SSH_ARGS=(-N -L "$FORWARD"
  -o ExitOnForwardFailure=yes
  -o ServerAliveInterval=30
  -o ServerAliveCountMax=3)
if [ -n "$IDENTITY" ]; then
  SSH_ARGS+=(-i "$IDENTITY" -o IdentitiesOnly=yes)
fi
if [ "$BACKGROUND" -eq 1 ]; then
  SSH_ARGS+=(-f)
fi
SSH_ARGS+=(-- "$HOST")

print_base_url() {
  printf 'ANTAR_CLOUD__BASE_URL=http://127.0.0.1:%s/v1\n' "$LOCAL_PORT"
}

if [ "$DRY_RUN" -eq 1 ]; then
  printf '# dry run: not connecting\n'
  printf 'ssh'
  printf ' %q' "${SSH_ARGS[@]}"
  printf '\n'
  print_base_url
  exit 0
fi

if [ "$BACKGROUND" -eq 1 ]; then
  # -f with ExitOnForwardFailure=yes: ssh returns only once the forward is up,
  # and fails if the local port is taken.
  if ! ssh "${SSH_ARGS[@]}"; then
    printf 'error: ssh could not open the tunnel (is local port %s free?)\n' "$LOCAL_PORT" >&2
    exit 1
  fi
  printf 'Tunnel is up in the background.\n'
  print_base_url
  printf 'To close it, find the ssh process and kill it:\n'
  printf '  pgrep -fl %s\n  kill <PID>\n' "$FORWARD"
  exit 0
fi

printf 'Opening tunnel in the foreground. Set this in the shell that runs Antar:\n'
print_base_url
printf 'Press Ctrl-C here to close the tunnel.\n'
exec ssh "${SSH_ARGS[@]}"
