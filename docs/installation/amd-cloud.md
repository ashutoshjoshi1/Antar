# AMD cloud setup

> **Remote execution is not implemented.** Today Antar validates an AMD cloud profile and
> displays it. It does not connect to the host, run jobs, or start any resource. This page
> describes how to declare a host now and what will be needed later.

Cloud setup is separate from [local installation](local.md) on purpose: nothing here is
required to develop or run Antar.

## What Antar assumes — and does not

Antar assumes only that you have SSH access to a Linux machine with an AMD GPU and a
working ROCm installation. It does **not** assume that cloud credits or a particular
program provide:

- a specific GPU model or count,
- a specific ROCm, driver, or OS version,
- persistent storage, object storage, or a shared filesystem,
- a public IP address, open ports, or a public endpoint,
- any particular SSH user, key arrangement, or bastion.

Check what your account actually provisions and declare it. Antar records what you declare
and will verify it on the host before running anything once remote execution exists.

## Declare a profile

Add to `configs/antar.yaml` (git-ignored):

```yaml
amd_cloud:
  name: my-amd-host
  ssh_host: 203.0.113.10
  ssh_user: ubuntu
  ssh_port: 22
  ssh_key_path: ~/.ssh/id_ed25519
  remote_workdir: ~/antar
  rocm_version: "6.4"        # whatever `cat /opt/rocm/.info/version` reports on your host
  gpus:
    - name: AMD Instinct MI300X   # whatever your instance actually has
      count: 1
      vram_gb: 192
```

Then:

```bash
uv run antar backends
# amd_cloud  not_implemented  Profile 'my-amd-host' is valid, but remote execution is not implemented. ...
```

A standalone example is in `configs/hardware/amd-cloud.example.yaml`.

## Credentials

- Private keys stay outside the repository. `ssh_key_path` is a path, never key material.
- `.gitignore` excludes `configs/antar.yaml`, `*.local.yaml`, `.env`, and common key
  filenames.
- The API never returns the key path; it reports only whether one is configured.

## Preparing the host for later milestones

When remote execution lands (roadmap M3), the host will need Python 3.11+, uv, and a ROCm
build of PyTorch that matches the host's ROCm version.

ROCm wheels are **not** part of Antar's dependency lock and must never be installed on the
macOS development machine. Install them on the host only, using the index URL that the
[PyTorch installation selector](https://pytorch.org/get-started/locally/) gives for your
ROCm version, and confirm against the
[ROCm documentation](https://rocm.docs.amd.com/) for your GPU and OS. Versions change
often; do not copy a version number from this file.

## Cost

Antar will never start, resize, or keep alive a paid resource without an explicit action
from you. Starting and stopping instances is, and will remain, your responsibility — stop
your instance when you are not using it.
