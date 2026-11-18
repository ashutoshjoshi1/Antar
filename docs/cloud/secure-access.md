# Secure access to the cloud endpoint

## What is being protected

- **The inference server.** A vLLM port open to the internet lets anyone spend your GPU
  time and read whatever is sent to it.
- **Credentials**: the vLLM API key, your SSH key, and a Hugging Face token if you use one.
- **Your machine.** Antar's API must not become a way to make HTTP requests to arbitrary
  hosts or run arbitrary commands.
- **Uploaded images**, which may be private.

Antar is a local developer tool. Its own API has no authentication and binds to
`127.0.0.1`; do not expose it.

## The SSH tunnel

vLLM listens on `127.0.0.1` on the host, and only there: `start_vllm.sh` publishes the port
as `127.0.0.1:PORT:8000` and has no option to change that. You reach it through a tunnel.

```bash
scripts/cloud/start_ssh_tunnel.sh --host my-amd-host
```

This forwards `127.0.0.1:18000` on your machine to `127.0.0.1:8000` on the host, with both
ends on loopback, and prints the setting to use:

```bash
export ANTAR_CLOUD__BASE_URL=http://127.0.0.1:18000/v1
```

Options: `--local-port`, `--remote-port`, `--identity PATH`, `--background`, `--dry-run`
(prints the `ssh` command without connecting). `--host` is an alias from `~/.ssh/config` or
`user@host`. Close a foreground tunnel with Ctrl-C.

Traffic between your machine and the host is encrypted by SSH, so plain `http://` to the
loopback end of the tunnel is appropriate.

## Which endpoints Antar will talk to

The rule is enforced when settings load (`CloudEndpointSettings` in
`antar/backends/amd_cloud/config.py`). A `cloud.base_url` is accepted only if:

- its host is loopback (`localhost`, `127.0.0.0/8`, `::1`), **or**
- its host is listed in `cloud.trusted_hosts` **and** the URL uses `https` **and** an API
  key is configured.

Anything else is a configuration error and Antar does not start. A URL with embedded
credentials is always rejected. The cloud client ignores `HTTP_PROXY`, `HTTPS_PROXY`, and
`ALL_PROXY`, so a proxy set in the environment cannot reroute the key or images, and it
never follows redirects.

```yaml
cloud:
  base_url: https://gpu.example.com/v1
  trusted_hosts: [gpu.example.com]     # your explicit authorization
```

Exposing vLLM beyond loopback is your decision and needs TLS and authentication in front of
it, which is outside what these scripts set up. The tunnel is the supported approach.

## No URL or command comes from a request

- Inference requests name a backend (`"backend": "amd_cloud"`). There is no parameter
  anywhere in the API that takes a URL. An unknown backend name, including a URL, is
  rejected.
- The only HTTP destinations are the Lemonade URL and the cloud URL in the server's own
  configuration.
- Text a user or a model writes is only ever sent as message content. It is never
  interpreted as a destination or a command.
- Over SSH, Antar sends only command strings defined in its own code: the `amd-smi` calls
  in `antar/backends/amd_cloud/amd_smi.py`, and `bash -s -- --machine` with the repository's
  preflight script on standard input. The SSH target comes from configuration, is validated
  against a conservative pattern, and is passed after `--` so it cannot be read as an
  option.
- The dashboard has no way to submit a command. Its cloud actions are fixed: read status,
  read GPU readings, run the preflight, save the cost session, register or remove the
  Lemonade provider.
- Registering with Lemonade uses the configured URL, never one from the request.

## API keys

**On the host.** Put the key in a file with mode 600 and pass `--api-key-file`.
`start_vllm.sh` hands it to the container as `VLLM_API_KEY` through a temporary env file
that it deletes after start, so the key does not appear in `ps`. Anyone who can run
`docker inspect` on the host can still read it.

**On your machine.** Set `ANTAR_CLOUD__API_KEY` in the environment or `.env` (git-ignored).
Never put it in YAML. The API and dashboard report only whether a key is configured.

**What the key protects.** Per
[vLLM's security page](https://docs.vllm.ai/en/stable/usage/security/), the key guards the
`/v1` routes. `/health`, `/version`, `/metrics`, and others stay open. That is one more
reason the port is loopback-only.

**SSH keys.** Antar never reads, copies, or prints a private key. `ssh_key_path` is a path
handed to `ssh`. The API reports only whether one is configured.

**Hugging Face token.** `HF_TOKEN` is forwarded to the container by name and is never
printed or written by the scripts.

Rotate any key that may have been exposed: write a new key file, restart vLLM, update
`ANTAR_CLOUD__API_KEY`.

## Images

Uploaded images are validated in memory (declared type, real file signature, size limit),
forwarded to the selected backend as data URLs, and never written to disk or to logs by
Antar. A cloud vision request sends the image to your own vLLM server through the tunnel
and nowhere else. Benchmark and comparison reports store prompts and responses, not image
bytes; the benchmark images are the bundled synthetic ones. If the server's error message
quotes an image back, Antar removes the image data and shortens the message before it is
shown, logged, or saved in a report.

Model responses are saved in reports. Treat `data/` as private if your prompts are.

## Lemonade provider registration (Path B)

Registering the endpoint with Lemonade (`POST /api/v1/cloud/lemonade-provider` with
`"confirm": true`, or the button in Settings) does two things you should know about:

- It changes Lemonade's configuration: the provider's URL is stored in Lemonade's
  `config.json`.
- It hands Lemonade the endpoint's API key. Lemonade holds runtime keys in memory only, so
  the key is gone after Lemonade restarts and must be registered again.

Lemonade refuses to send a key to an `http://` URL unless told `allow_insecure_http: true`.
Antar sets that flag only when the configured URL is `http://`. For a loopback tunnel this
is safe in the way that matters: the plaintext hop is between two processes on your own
machine, and SSH encrypts the rest. Lemonade still shows its own warnings about it, and the
dashboard repeats them verbatim. Do not use this with an `http://` URL that is not
loopback; the endpoint rule above already prevents configuring one.

Antar registers only with a Lemonade on this machine. If `ANTAR_LEMONADE__BASE_URL` points
at another host, registration is refused (422): the key would cross the network to that
host, and a loopback endpoint address would mean a different machine there.

Remove the provider with `DELETE /api/v1/cloud/lemonade-provider` or the Remove button.

Cloud routing is experimental in Lemonade.

## Connection health and reconnecting

`GET /api/v1/cloud/status`, the AMD Cloud page, and `uv run antar cloud-status` report one
of:

| State | Meaning |
|---|---|
| `not_configured` | No `cloud.base_url` |
| `unavailable`, "Could not connect … Is the SSH tunnel open and vLLM running?" | The tunnel is down or nothing is listening |
| `unavailable`, "vLLM is starting: the model is still loading (503)" | Wait |
| `unavailable`, "rejected the request (401)" | Key mismatch |
| `available` | Connected; the served models and vLLM version are shown |

A dropped tunnel is a status, never a crash. A request in flight fails with "Lost the
connection to the cloud endpoint", a running comparison records the failed requests and
continues, and local inference is unaffected. To reconnect, start the tunnel again; nothing
in Antar needs restarting.

Connection attempts time out after `cloud.timeout_seconds` (5 by default). A generation is
abandoned after `cloud.generation_timeout_seconds` of silence (600 by default).
