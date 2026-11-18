# Security Policy

## Supported versions

Antar is pre-alpha. Only the `main` branch receives security fixes.

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private reporting:
<https://github.com/ashutoshjoshi1/Antar/security/advisories/new>

Include what you found, how to reproduce it, and the impact you expect. You should receive
an acknowledgement within a few days. Please allow time for a fix before disclosing
publicly.

## Security model

Knowing what Antar is designed for helps you judge what counts as a vulnerability.

- **The API is a local developer tool.** It has no authentication and binds to `127.0.0.1`
  by default. It can run inference, load and unload models, start confirmed downloads, and
  run benchmarks, so do not expose it to an untrusted network.
- **Inference targets are fixed by configuration.** Requests choose a backend by name.
  Nothing in the API accepts a URL, so it cannot be used to make the server call arbitrary
  hosts.
- **Uploaded images** are validated by type, file signature, and size, held in memory, and
  forwarded only to the backend the request names: the configured Lemonade server, or the
  configured cloud endpoint. They are never written to disk or to logs.
- **Model output is rendered as text**, never as HTML.
- **CORS** is restricted to the configured dashboard origins.
- **Secrets** (the Lemonade and cloud endpoint API keys) are read from the environment or `.env`, held as
  `SecretStr`, and never returned by the API. URLs containing embedded credentials are
  rejected.
- **AMD cloud profiles** are validated so host, user, and working-directory values cannot
  be interpreted as SSH options or shell syntax. Over SSH, Antar runs only fixed, read-only
  commands defined in its own code, with `BatchMode=yes`; it never reads a private key.
- **The cloud endpoint** must be a loopback address, or a host listed in
  `cloud.trusted_hosts` that uses HTTPS and has an API key. Anything else is refused when
  settings load. See [docs/cloud/secure-access.md](docs/cloud/secure-access.md).
- **Running model-written code** to score the unit-tested coding workload is off by
  default. When enabled it runs in a separate process with a time limit, which is not a
  security sandbox.
- **Cloud resources** are never started, stopped, or resized by Antar.
- **Experiment ids** are validated against a strict pattern before they are used as file
  names.
- **Subprocesses** for hardware probing use fixed argument lists, never a shell.

## For contributors

- Never commit `.env`, `configs/antar.yaml`, private keys, or model weights. `.gitignore`
  covers these; do not weaken it.
- If a credential is committed by accident, rotate it immediately. Removing the commit is
  not enough.
- Model files downloaded from the internet are untrusted input. Prefer `safetensors` and
  GGUF over pickle-based formats.
