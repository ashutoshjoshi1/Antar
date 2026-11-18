#!/usr/bin/env bash
# Shared helpers for the Antar cloud operator scripts. Sourced, never executed.
#
# check_environment.sh and start_ssh_tunnel.sh do NOT source this file:
# the first must work when piped over ssh (`bash -s`), the second runs on the
# laptop. If you change ANTAR_DEFAULT_IMAGE here, change DEFAULT_IMAGE in
# check_environment.sh too.
#
# Written to run on bash 3.2+ (no associative arrays, no mapfile). Regex
# repetition bounds stay at or below 255 (POSIX RE_DUP_MAX).

# Default image. Tag and digest read from Docker Hub on 2026-11-18:
# v0.34.0-rocm100 == v0.34.0 == latest, built on ROCm 10.0.
# Image/driver compatibility has NOT been verified on real hardware by this
# project. Before using it, check the tag against your host's amdgpu driver in
# the ROCm compatibility matrix and override with --image if needed:
#   https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html
# ROCm 10.0 images use zstd-compressed layers: Docker 23+ (or containerd 1.5+).
# shellcheck disable=SC2034  # used by the scripts that source this file
ANTAR_DEFAULT_IMAGE='vllm/vllm-openai-rocm:v0.34.0-rocm100@sha256:3cb773d23f063afa86291ef75773cdd486154ddea94c213300f4ed7cc42b7af1'

# Where the official vLLM docker command mounts the Hugging Face cache
# (https://docs.vllm.ai/en/stable/deployment/docker/, checked 2026-11-18).
# shellcheck disable=SC2034
ANTAR_CONTAINER_HF_HOME='/root/.cache/huggingface'

# The port vLLM listens on inside the container (its documented default).
# shellcheck disable=SC2034
ANTAR_CONTAINER_PORT=8000

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage_error() {
  printf 'error: %s\n(run with --help for usage)\n' "$*" >&2
  exit 2
}

warn() {
  printf 'warning: %s\n' "$*" >&2
}

# require_value "$@" — call before reading "$2" for an option that takes a value.
require_value() {
  if [ "$#" -lt 2 ]; then
    usage_error "$1 requires a value"
  fi
}

utc_now() {
  date -u '+%Y-%m-%dT%H:%M:%SZ'
}

# --- validators (each exits with a usage error on bad input) -----------------

validate_model_id() {
  local re='^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+$'
  if ! [[ "$1" =~ $re ]]; then
    usage_error "--model must look like ORG/NAME (got an invalid value)"
  fi
}

validate_revision() {
  local re='^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$'
  if ! [[ "$1" =~ $re ]] || [[ "$1" == *..* ]]; then
    usage_error "--revision must be a branch, tag or commit hash ([A-Za-z0-9._/-], no '..')"
  fi
}

validate_image_ref() {
  local re='^[a-z0-9][A-Za-z0-9._/:@-]{0,254}$'
  if ! [[ "$1" =~ $re ]]; then
    usage_error "--image is not a valid image reference"
  fi
}

validate_container_name() {
  local re='^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$'
  if ! [[ "$1" =~ $re ]]; then
    usage_error "--name must match [A-Za-z0-9][A-Za-z0-9_.-]*"
  fi
}

# validate_int OPTION VALUE MIN MAX
validate_int() {
  local re='^(0|[1-9][0-9]{0,8})$'
  if ! [[ "$2" =~ $re ]] || [ "$2" -lt "$3" ] || [ "$2" -gt "$4" ]; then
    usage_error "$1 must be an integer between $3 and $4"
  fi
}

validate_port() {
  validate_int "$1" "$2" 1 65535
}

# An absolute directory path that is safe to hand to `docker -v`.
validate_abs_dir_path() {
  local re='^/[A-Za-z0-9._/@+-]*$'
  if ! [[ "$2" =~ $re ]]; then
    usage_error "$1 must be an absolute path using only [A-Za-z0-9._/@+-]"
  fi
}

# --- JSON (no jq on the host; every value is validated before it gets here) --

json_string() {
  local s="$1"
  local re='[[:cntrl:]]'
  if [[ "$s" =~ $re ]]; then
    die "refusing to write a control character into JSON"
  fi
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  printf '"%s"' "$s"
}

# json_string_or_null VALUE — empty means "not set" and becomes null.
json_string_or_null() {
  if [ -z "$1" ]; then
    printf 'null'
  else
    json_string "$1"
  fi
}

# json_raw_or_null VALUE — for already-validated integers.
json_raw_or_null() {
  if [ -z "$1" ]; then
    printf 'null'
  else
    printf '%s' "$1"
  fi
}

# --- filesystem ---------------------------------------------------------------

# Prints the directory Antar's record files live in, creating it if needed.
antar_remote_dir() {
  local dir="${ANTAR_REMOTE_DIR:-${HOME:?HOME is not set}/antar}"
  case "$dir" in
    /*) ;;
    *) die "ANTAR_REMOTE_DIR must be an absolute path" ;;
  esac
  mkdir -p "$dir" || die "cannot create $dir"
  printf '%s' "$dir"
}

# write_file_atomic PATH — writes stdin to PATH via a temp file in the same dir.
write_file_atomic() {
  local target="$1" tmp
  tmp="$(mktemp "${target}.XXXXXX")" || die "cannot create a temp file next to $target"
  if ! cat > "$tmp"; then
    rm -f "$tmp"
    die "cannot write $target"
  fi
  mv "$tmp" "$target" || die "cannot move $tmp to $target"
}

file_mode() {
  # GNU stat first, BSD stat second.
  stat -c '%a' "$1" 2>/dev/null || stat -f '%Lp' "$1"
}

# read_api_key_file PATH — sets ANTAR_API_KEY. The key is never printed.
ANTAR_API_KEY=''
read_api_key_file() {
  local path="$1" mode key
  local re='^[A-Za-z0-9._~+/=-]{1,255}$'
  if [ ! -f "$path" ] || [ ! -r "$path" ]; then
    die "--api-key-file: $path is not a readable regular file"
  fi
  mode="$(file_mode "$path")" || die "--api-key-file: cannot read the mode of $path"
  if [ "$mode" != "600" ] && [ "$mode" != "400" ]; then
    die "--api-key-file: $path has mode $mode; run: chmod 600 $path"
  fi
  key="$(cat "$path")"
  if ! [[ "$key" =~ $re ]]; then
    die "--api-key-file: $path must hold one line of 1-255 characters from [A-Za-z0-9._~+/=-]"
  fi
  ANTAR_API_KEY="$key"
}

# --- docker -------------------------------------------------------------------

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    die "docker is not installed or not on PATH (run check_environment.sh)"
  fi
  if ! docker ps >/dev/null 2>&1; then
    die "docker is not usable without sudo by this user (run check_environment.sh)"
  fi
}

# Pulling a multi-GB image is the operator's explicit action; never implicit.
require_local_image() {
  if ! docker image inspect "$1" >/dev/null 2>&1; then
    die "image is not present locally. Pull it yourself first: docker pull $1"
  fi
}
