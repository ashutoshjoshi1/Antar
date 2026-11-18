# AMD cloud setup

> Cloud inference is implemented and has **not yet run on real AMD hardware**. See
> [Phase 2](../phase2-amd-cloud.md) for what is verified and what is not.

Cloud setup is separate from [local installation](local.md) on purpose: nothing here is
required to develop or run Antar.

This page is now an index. The procedure lives in:

1. [AMD host setup](../cloud/amd-setup.md) — what the host needs, SSH keys, configuring
   Antar, the preflight, the memory estimate, the model catalog.
2. [ROCm and vLLM](../cloud/rocm-vllm.md) — the container image, and a command-by-command
   runbook for downloading weights and serving a model.
3. [Secure access](../cloud/secure-access.md) — the SSH tunnel, which endpoints Antar will
   talk to, and key handling.
4. [Local versus cloud](../benchmarks/local-vs-cloud.md) — running and reading a
   comparison.
5. [Operator checklist](../challenge/phase2-demo.md#operator-checklist) — saving results
   and shutting down.

## What Antar assumes — and does not

Antar assumes only that you have SSH access to a Linux machine with AMD GPUs and Docker. It
does **not** assume that cloud credits or a particular program provide:

- a specific GPU model or count,
- a specific ROCm, driver, or OS version,
- persistent storage, object storage, or a shared filesystem,
- a public IP address, open ports, or a public endpoint,
- any particular SSH user, key arrangement, or bastion.

Run the preflight and read what your host actually has.

## Credentials

- Private keys stay outside the repository. `ssh_key_path` is a path, never key material,
  and Antar only hands it to `ssh`.
- `.gitignore` excludes `configs/antar.yaml`, `*.local.yaml`, `.env`, and common key
  filenames.
- The API never returns a key or a key path; it reports only whether one is configured.

## Training dependencies

Inference needs nothing installed on the host but Docker: the vLLM container carries its
own ROCm userspace and PyTorch. When fine-tuning lands, the host will also need a ROCm
build of PyTorch matching its ROCm version. ROCm wheels are **not** part of Antar's
dependency lock and must never be installed on the macOS development machine.

## Cost

Antar never starts, resizes, or keeps alive a paid resource. Starting and stopping
instances is your responsibility, and Antar cannot confirm that an instance has stopped.
It estimates spending from an hourly price and a start time that you enter, stops a
comparison at a time budget, and asks for confirmation before a comparison uses cloud
time. Stop your instance when you are not using it.
