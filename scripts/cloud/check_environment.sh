#!/usr/bin/env bash
# check_environment.sh — read-only preflight for an AMD Instinct (ROCm) Linux
# host that will run vLLM in Docker for Antar.
#
# Runs ON THE REMOTE HOST. Self-contained on purpose so it also works piped:
#   ssh HOST bash -s -- --machine < check_environment.sh
#
# It only reads. It never installs or changes drivers, never uses sudo, never
# pulls an image, and never starts a container.
#
# Sources checked 2026-11-18:
#   - https://docs.vllm.ai/en/stable/deployment/docker/ : the ROCm container
#     needs /dev/kfd and /dev/dri; official image is vllm/vllm-openai-rocm.
#   - Docker Hub: v0.34.0-rocm100 is built on ROCm 10.0, whose images use zstd
#     layers (Docker 23+ or containerd 1.5+).
#   - AMD ROCm docs: `lsmod | grep amdgpu`; docker must work without sudo;
#     `sudo usermod -aG video,render $USER` is the documented group remediation.
#   - amd-smi JSON/text field names are not documented, so this script does not
#     parse them. GPU count and VRAM come from sysfs, model names from lspci.
#
# NOT verified on real AMD hardware by this project.
set -euo pipefail

# Keep in sync with ANTAR_DEFAULT_IMAGE in _common.sh. Re-check the tag against
# your host's amdgpu driver before use:
#   https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html
DEFAULT_IMAGE='vllm/vllm-openai-rocm:v0.34.0-rocm100@sha256:3cb773d23f063afa86291ef75773cdd486154ddea94c213300f4ed7cc42b7af1'
AMD_PCI_VENDOR='0x1002'
MIN_DOCKER_MAJOR=23
COMMAND_TIMEOUT_SECONDS=20
MAX_FIELD_CHARS=500

usage() {
  cat <<'EOF'
Usage: check_environment.sh [--machine] [--image REF] [--model-cache DIR]
                            [--min-disk-gb N]

Read-only preflight for the remote AMD GPU host. Changes nothing.

  --machine          print only machine-readable lines (see below)
  --image REF        image to look for locally (default: the pinned
                     vllm/vllm-openai-rocm image; it is never pulled)
  --model-cache DIR  Hugging Face cache directory (default: $HOME/.cache/huggingface)
  --min-disk-gb N    free space required on the cache filesystem (default: 100)
  -h, --help         show this help

Machine output, tab-separated, no tabs or newlines inside a field:
  ANTAR_CHECK<TAB>id<TAB>pass|warn|fail|skip<TAB>detail<TAB>remediation
  ANTAR_FACT<TAB>key<TAB>value
A fact is printed only when the value was actually read from the host.

Exit status: 0 no check failed, 1 at least one check failed, 2 bad arguments.

Piped use:  ssh HOST bash -s -- --machine < check_environment.sh
EOF
}

usage_error() {
  printf 'error: %s\n(run with --help for usage)\n' "$*" >&2
  exit 2
}

MACHINE=0
IMAGE="$DEFAULT_IMAGE"
MODEL_CACHE=''
MIN_DISK_GB=100

while [ "$#" -gt 0 ]; do
  case "$1" in
    --machine) MACHINE=1; shift ;;
    --image | --model-cache | --min-disk-gb)
      if [ "$#" -lt 2 ]; then usage_error "$1 requires a value"; fi
      case "$1" in
        --image) IMAGE="$2" ;;
        --model-cache) MODEL_CACHE="$2" ;;
        --min-disk-gb) MIN_DISK_GB="$2" ;;
      esac
      shift 2
      ;;
    -h | --help) usage; exit 0 ;;
    *) usage_error "unknown argument: $1" ;;
  esac
done

IMAGE_RE='^[a-z0-9][A-Za-z0-9._/:@-]{0,254}$'
PATH_RE='^/[A-Za-z0-9._/@+-]*$'
INT_RE='^[1-9][0-9]{0,5}$'
if ! [[ "$IMAGE" =~ $IMAGE_RE ]]; then
  usage_error "--image is not a valid image reference"
fi
if [ -z "$MODEL_CACHE" ]; then
  if [ -z "${HOME:-}" ]; then usage_error "HOME is not set; pass --model-cache DIR"; fi
  MODEL_CACHE="${HOME}/.cache/huggingface"
fi
if ! [[ "$MODEL_CACHE" =~ $PATH_RE ]]; then
  usage_error "--model-cache must be an absolute path using only [A-Za-z0-9._/@+-]"
fi
if ! [[ "$MIN_DISK_GB" =~ $INT_RE ]]; then
  usage_error "--min-disk-gb must be a positive integer"
fi

# --- output -------------------------------------------------------------------

FAILED=0
REMEDIATIONS=''
FACT_LINES=''

# Replace tabs/newlines so a field can never break the tab-separated contract.
clean() {
  local s="$1"
  s="${s//$'\t'/ }"
  s="${s//$'\n'/ }"
  s="${s//$'\r'/ }"
  printf '%s' "${s:0:$MAX_FIELD_CHARS}"
}

# check ID STATUS DETAIL [REMEDIATION]
check() {
  local id="$1" status="$2" detail remediation
  detail="$(clean "${3-}")"
  remediation="$(clean "${4-}")"
  if [ "$status" = "fail" ]; then FAILED=1; fi
  if [ "$MACHINE" -eq 1 ]; then
    printf 'ANTAR_CHECK\t%s\t%s\t%s\t%s\n' "$id" "$status" "$detail" "$remediation"
    return 0
  fi
  printf '%-19s %-5s %s\n' "$id" "$status" "$detail"
  if [ -n "$remediation" ] && { [ "$status" = "fail" ] || [ "$status" = "warn" ]; }; then
    REMEDIATIONS="${REMEDIATIONS}  [${status}] ${id}: ${remediation}"$'\n'
  fi
}

# fact KEY VALUE — skipped when VALUE is empty (nothing was read).
fact() {
  local key="$1" value
  value="$(clean "${2-}")"
  if [ -z "$value" ]; then return 0; fi
  if [ "$MACHINE" -eq 1 ]; then
    printf 'ANTAR_FACT\t%s\t%s\n' "$key" "$value"
  else
    FACT_LINES="${FACT_LINES}  ${key} = ${value}"$'\n'
  fi
}

have() {
  command -v "$1" >/dev/null 2>&1
}

with_timeout() {
  if have timeout; then
    timeout "$COMMAND_TIMEOUT_SECONDS" "$@"
  else
    "$@"
  fi
}

# Prints the value of KEY from /etc/os-release without sourcing the file.
os_release_value() {
  sed -n "s/^$1=//p" /etc/os-release 2>/dev/null | head -n 1 | sed -e 's/^"//' -e 's/"$//' || true
}

if [ "$MACHINE" -eq 0 ]; then
  printf '%-19s %-5s %s\n' 'CHECK' 'STATE' 'DETAIL'
fi

# --- os, arch -----------------------------------------------------------------

KERNEL_NAME="$(uname -s 2>/dev/null || true)"
KERNEL_RELEASE="$(uname -r 2>/dev/null || true)"
HOST_NAME="$(hostname 2>/dev/null || uname -n 2>/dev/null || true)"
fact hostname "$HOST_NAME"
fact kernel "$KERNEL_RELEASE"

if [ "$KERNEL_NAME" != "Linux" ]; then
  check os fail "kernel is '${KERNEL_NAME}', not Linux" \
    "Run this on the Linux GPU host, not on your laptop."
elif [ -r /etc/os-release ]; then
  OS_NAME="$(os_release_value NAME)"
  OS_VERSION="$(os_release_value VERSION_ID)"
  fact os_name "$OS_NAME"
  fact os_version "$OS_VERSION"
  check os pass "${OS_NAME:-unknown} ${OS_VERSION:-} (kernel ${KERNEL_RELEASE})"
else
  check os warn "Linux, but /etc/os-release is not readable (kernel ${KERNEL_RELEASE})" \
    "Confirm the distribution is one AMD lists in the ROCm compatibility matrix."
fi

ARCH="$(uname -m 2>/dev/null || true)"
fact arch "$ARCH"
if [ "$ARCH" = "x86_64" ]; then
  check arch pass "x86_64"
else
  check arch fail "architecture is '${ARCH}'; x86_64 is required" \
    "Use an x86_64 host. The vllm/vllm-openai-rocm image is built for x86_64."
fi

# --- GPUs (sysfs first, lspci as fallback; amd-smi output is never parsed) -----

GPU_SOURCE=''
GPU_SLOTS=()
AMD_CARDS=()
for card in /sys/class/drm/card*; do
  if ! [[ "${card##*/}" =~ ^card[0-9]+$ ]]; then continue; fi
  if [ ! -r "${card}/device/vendor" ]; then continue; fi
  vendor="$(cat "${card}/device/vendor" 2>/dev/null || true)"
  if [ "$vendor" = "$AMD_PCI_VENDOR" ]; then
    AMD_CARDS+=("$card")
    slot="$(readlink -f "${card}/device" 2>/dev/null || true)"
    GPU_SLOTS+=("${slot##*/}")
  fi
done

if [ "${#AMD_CARDS[@]}" -gt 0 ]; then
  GPU_SOURCE='sysfs'
elif have lspci; then
  # PCI class 03xx = display controller, 1200 = processing accelerator.
  while IFS= read -r slot; do
    if [ -n "$slot" ]; then GPU_SLOTS+=("$slot"); fi
  done < <(lspci -n -d 1002: 2>/dev/null | awk '$2 ~ /^(03[0-9a-f][0-9a-f]|1200):$/ {print $1}')
  if [ "${#GPU_SLOTS[@]}" -gt 0 ]; then GPU_SOURCE='lspci'; fi
fi
GPU_COUNT="${#GPU_SLOTS[@]}"

case "$GPU_SOURCE" in
  sysfs)
    check gpu_vendor pass "AMD (${AMD_PCI_VENDOR}) DRM device(s) found in /sys/class/drm"
    check gpu_count pass "${GPU_COUNT} AMD DRM device(s) (sysfs; includes any AMD integrated graphics)"
    fact gpu_count "$GPU_COUNT"
    ;;
  lspci)
    check gpu_vendor pass "AMD (${AMD_PCI_VENDOR}) GPU found by lspci, but no AMD DRM card in /sys/class/drm"
    check gpu_count warn "${GPU_COUNT} AMD GPU PCI device(s) by lspci; none bound to a DRM driver" \
      "Load the amdgpu driver (see the amdgpu_driver check). This script does not install drivers."
    fact gpu_count "$GPU_COUNT"
    ;;
  *)
    if [ ! -d /sys/class/drm ] && ! have lspci; then
      check gpu_vendor fail "cannot look for GPUs: no /sys/class/drm and lspci is not installed" \
        "Install pciutils (lspci), or check that this is the GPU host."
    else
      check gpu_vendor fail "no AMD (${AMD_PCI_VENDOR}) GPU found in /sys/class/drm or lspci" \
        "This host has no visible AMD GPU. Check the instance type in your provider console."
    fi
    check gpu_count fail "0 AMD GPUs found" "See gpu_vendor."
    ;;
esac

if [ "$GPU_COUNT" -eq 0 ]; then
  check gpu_model skip "no AMD GPU found"
  check gpu_memory skip "no AMD GPU found"
else
  # Model names: lspci only (the PCI ID database). sysfs has no product name.
  GPU_MODELS=''
  if have lspci; then
    for slot in "${GPU_SLOTS[@]}"; do
      name="$(lspci -vmm -s "$slot" 2>/dev/null | sed -n 's/^Device:[[:space:]]*//p' | tail -n 1 || true)"
      if [ -z "$name" ]; then continue; fi
      case "; ${GPU_MODELS}; " in
        *"; ${name}; "*) ;;
        *) GPU_MODELS="${GPU_MODELS:+${GPU_MODELS}; }${name}" ;;
      esac
    done
  fi
  if [ -n "$GPU_MODELS" ]; then
    check gpu_model pass "${GPU_MODELS} (lspci)"
    fact gpu_model "$GPU_MODELS"
  else
    check gpu_model warn "model name not readable (lspci missing or returned no device name)" \
      "Install pciutils for names, or read the model with: amd-smi static"
  fi

  # VRAM: amdgpu's sysfs file, in bytes. One value per GPU, in card order.
  VRAM_LIST=''
  VRAM_UNREADABLE=0
  VRAM_DIFFERS=0
  VRAM_FIRST=''
  if [ "${#AMD_CARDS[@]}" -gt 0 ]; then
    for card in "${AMD_CARDS[@]}"; do
      bytes="$(cat "${card}/device/mem_info_vram_total" 2>/dev/null || true)"
      if ! [[ "$bytes" =~ ^[0-9]+$ ]]; then
        VRAM_UNREADABLE=1
        continue
      fi
      mb=$((bytes / 1048576))
      if [ -z "$VRAM_FIRST" ]; then VRAM_FIRST="$mb"; fi
      if [ "$mb" != "$VRAM_FIRST" ]; then VRAM_DIFFERS=1; fi
      VRAM_LIST="${VRAM_LIST:+${VRAM_LIST},}${mb}"
    done
  fi
  if [ -z "$VRAM_LIST" ] || [ "$VRAM_UNREADABLE" -eq 1 ]; then
    check gpu_memory warn "VRAM not readable from /sys/class/drm/card*/device/mem_info_vram_total" \
      "Needs the amdgpu driver loaded. Read it by hand with: amd-smi static"
  elif [ "$VRAM_DIFFERS" -eq 1 ]; then
    check gpu_memory pass "per-GPU VRAM in MiB, card order: ${VRAM_LIST} (sysfs)"
    fact gpu_vram_mb "$VRAM_LIST"
  else
    check gpu_memory pass "${VRAM_FIRST} MiB per GPU (sysfs)"
    fact gpu_vram_mb "$VRAM_FIRST"
  fi
fi

# --- driver, ROCm, amd-smi ----------------------------------------------------

if [ -d /sys/module/amdgpu ]; then
  AMDGPU_VERSION="$(cat /sys/module/amdgpu/version 2>/dev/null || true)"
  fact amdgpu_version "$AMDGPU_VERSION"
  if [ -n "$AMDGPU_VERSION" ]; then
    check amdgpu_driver pass "amdgpu loaded, module version ${AMDGPU_VERSION}"
  else
    check amdgpu_driver pass "amdgpu loaded (in-kernel driver; no separate module version)"
  fi
else
  check amdgpu_driver fail "amdgpu kernel module is not loaded (no /sys/module/amdgpu)" \
    "Install/load the amdgpu driver per AMD's ROCm install guide, then confirm with: lsmod | grep amdgpu. This script does not install drivers."
fi

ROCM_VERSION=''
for version_file in /opt/rocm/.info/version /opt/rocm-*/.info/version; do
  if [ -r "$version_file" ]; then
    ROCM_VERSION="$(head -n 1 "$version_file" 2>/dev/null || true)"
    if [ -n "$ROCM_VERSION" ]; then break; fi
  fi
done
if [ -n "$ROCM_VERSION" ]; then
  fact rocm_version "$ROCM_VERSION"
  check rocm_runtime pass "host ROCm ${ROCM_VERSION}"
elif have rocminfo; then
  check rocm_runtime pass "rocminfo is installed; no /opt/rocm/.info/version to read a version from"
else
  check rocm_runtime warn "no ROCm userspace on the host; not required, the container image carries its own ROCm userspace" \
    "Nothing to do for Docker use. Only the amdgpu kernel driver must match the image (ROCm compatibility matrix)."
fi

if have amd-smi; then
  AMD_SMI_OUT=''
  if AMD_SMI_OUT="$(with_timeout amd-smi version 2>/dev/null)" && [ -n "$AMD_SMI_OUT" ]; then
    # Format is undocumented: pass the first line through as-is, unparsed.
    AMD_SMI_LINE="$(printf '%s\n' "$AMD_SMI_OUT" | head -n 1 || true)"
    fact amd_smi_version "$AMD_SMI_LINE"
    check amd_smi pass "$AMD_SMI_LINE"
  else
    check amd_smi warn "amd-smi is installed but 'amd-smi version' failed or printed nothing" \
      "Run 'amd-smi version' by hand. If it reports missing groups: sudo usermod -aG video,render \$USER, then log out and in."
  fi
else
  check amd_smi warn "amd-smi not found; Antar cannot collect GPU telemetry without it" \
    "Install AMD SMI per AMD's ROCm docs if you want GPU metrics. Serving works without it."
fi

# --- device nodes -------------------------------------------------------------

if [ -c /dev/kfd ]; then
  if [ -r /dev/kfd ] && [ -w /dev/kfd ]; then
    check dev_kfd pass "/dev/kfd present"
  else
    check dev_kfd warn "/dev/kfd present, but this user cannot open it directly (Docker can still pass it through)" \
      "For non-Docker tools such as amd-smi: sudo usermod -aG video,render \$USER, then log out and in."
  fi
else
  check dev_kfd fail "/dev/kfd is missing" \
    "It appears when the amdgpu driver is loaded on a supported GPU. See amdgpu_driver."
fi

RENDER_NODES=0
for node in /dev/dri/renderD*; do
  if [ -c "$node" ]; then RENDER_NODES=$((RENDER_NODES + 1)); fi
done
if [ "$RENDER_NODES" -gt 0 ]; then
  check dev_dri pass "${RENDER_NODES} render node(s) in /dev/dri"
else
  check dev_dri fail "no /dev/dri/renderD* nodes" \
    "They appear when the amdgpu driver is loaded. See amdgpu_driver."
fi

# --- docker -------------------------------------------------------------------

DOCKER_USABLE=0
if ! have docker; then
  check docker fail "docker is not installed or not on PATH" \
    "Install Docker Engine ${MIN_DOCKER_MAJOR}+ from docs.docker.com/engine/install."
  check docker_permissions skip "docker not installed"
  check docker_version skip "docker not installed"
else
  check docker pass "$(command -v docker)"
  if with_timeout docker ps >/dev/null 2>&1; then
    DOCKER_USABLE=1
    check docker_permissions pass "docker ps works without sudo"
  else
    check docker_permissions fail "'docker ps' failed for this user (daemon stopped, or no permission)" \
      "Start the daemon, or add this user to the docker group per Docker's post-install docs (sudo usermod -aG docker \$USER), then log out and in. These scripts never use sudo."
  fi

  DOCKER_VERSION=''
  DOCKER_VERSION_FROM='server'
  if [ "$DOCKER_USABLE" -eq 1 ]; then
    DOCKER_VERSION="$(with_timeout docker version --format '{{.Server.Version}}' 2>/dev/null || true)"
  fi
  if [ -z "$DOCKER_VERSION" ]; then
    DOCKER_VERSION_FROM='client'
    DOCKER_VERSION="$(docker version --format '{{.Client.Version}}' 2>/dev/null || true)"
  fi
  DOCKER_MAJOR="${DOCKER_VERSION%%.*}"
  if ! [[ "$DOCKER_MAJOR" =~ ^[0-9]+$ ]]; then
    check docker_version warn "could not read a Docker version" \
      "Run 'docker version'. ROCm 10.0 images need Docker ${MIN_DOCKER_MAJOR}+ (zstd layers)."
  elif [ "$DOCKER_MAJOR" -lt "$MIN_DOCKER_MAJOR" ]; then
    fact docker_version "$DOCKER_VERSION"
    check docker_version fail "Docker ${DOCKER_VERSION} (${DOCKER_VERSION_FROM}); ${MIN_DOCKER_MAJOR}+ is needed for zstd image layers" \
      "Upgrade Docker Engine to ${MIN_DOCKER_MAJOR} or newer."
  elif [ "$DOCKER_VERSION_FROM" = "client" ]; then
    fact docker_version "$DOCKER_VERSION"
    check docker_version warn "Docker client ${DOCKER_VERSION}; the server version could not be read" \
      "Fix docker_permissions, then re-run."
  else
    fact docker_version "$DOCKER_VERSION"
    check docker_version pass "Docker ${DOCKER_VERSION} (server)"
  fi
fi

# --- disk, image, model cache -------------------------------------------------

DISK_PATH="$MODEL_CACHE"
while [ ! -e "$DISK_PATH" ] && [ "$DISK_PATH" != "/" ]; do
  DISK_PATH="$(dirname "$DISK_PATH")"
done
FREE_KB="$(df -Pk "$DISK_PATH" 2>/dev/null | awk 'NR == 2 {print $4}' || true)"
if [[ "$FREE_KB" =~ ^[0-9]+$ ]]; then
  FREE_GB=$((FREE_KB / 1048576))
  fact disk_free_gb "$FREE_GB"
  if [ "$FREE_GB" -ge "$MIN_DISK_GB" ]; then
    check disk_space pass "${FREE_GB} GB free on the filesystem holding ${DISK_PATH} (need ${MIN_DISK_GB})"
  else
    check disk_space fail "${FREE_GB} GB free on the filesystem holding ${DISK_PATH}; ${MIN_DISK_GB} required" \
      "Free space or attach a larger volume and pass it with --model-cache. Docker's own image store needs space too."
  fi
else
  check disk_space warn "could not read free space for ${DISK_PATH}" "Check by hand: df -h ${DISK_PATH}"
fi

if [ "$DOCKER_USABLE" -eq 1 ]; then
  if with_timeout docker image inspect "$IMAGE" >/dev/null 2>&1; then
    fact image_present true
    check image pass "present locally: ${IMAGE}"
  else
    fact image_present false
    check image warn "not pulled yet: ${IMAGE}" \
      "Pulling is your explicit action (a large download): docker pull ${IMAGE}"
  fi
else
  check image skip "docker is not usable, so the local image store was not read"
fi

if [ -d "$MODEL_CACHE" ]; then
  if [ -w "$MODEL_CACHE" ]; then
    check model_cache pass "${MODEL_CACHE} exists and is writable"
  else
    check model_cache fail "${MODEL_CACHE} exists but is not writable by this user" \
      "Fix ownership of the directory, or choose another with --model-cache."
  fi
elif [ -e "$MODEL_CACHE" ]; then
  check model_cache fail "${MODEL_CACHE} exists but is not a directory" \
    "Choose another path with --model-cache."
else
  check model_cache warn "${MODEL_CACHE} does not exist yet" \
    "Create it as your user before starting a container (otherwise Docker creates it as root): mkdir -p ${MODEL_CACHE}"
fi

# --- summary ------------------------------------------------------------------

if [ "$MACHINE" -eq 0 ]; then
  if [ -n "$FACT_LINES" ]; then
    printf '\nFacts read from this host:\n%s' "$FACT_LINES"
  fi
  if [ -n "$REMEDIATIONS" ]; then
    printf '\nWhat to do:\n%s' "$REMEDIATIONS"
  fi
  if [ "$FAILED" -eq 1 ]; then
    printf '\nResult: at least one check FAILED. Nothing on this host was changed.\n'
  else
    printf '\nResult: no check failed. Nothing on this host was changed.\n'
  fi
fi

exit "$FAILED"
