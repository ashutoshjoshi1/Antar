# Local installation

Works on macOS (Apple Silicon is the primary development platform) and Linux. No GPU, no
cloud account, and no Lemonade install are required to run Antar itself.

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11 or newer | `python3 --version` |
| uv | recent | `uv --version` |
| Node.js | 22 or newer | `node --version` |
| pnpm | 10 or newer | `pnpm --version` |

## Install

```bash
uv sync
cd apps/web && pnpm install
```

`uv sync` installs the base dependencies only. PyTorch, Transformers, and PEFT are in the
optional `ml` extra and are not needed for anything that works today:

```bash
uv sync --extra ml    # only when working on training code
```

## Run

```bash
uv run antar serve              # API: http://localhost:8080  (docs at /docs)
cd apps/web && pnpm dev         # dashboard: http://localhost:5173
```

## Lemonade

Lemonade is required for inference and benchmarks; the rest of Antar runs without it.
Install it from <https://lemonade-server.ai>. On macOS it is a `.pkg` installer for Apple
Silicon. Once its server is running, Antar finds it at the documented default,
`http://localhost:13305/v1`.

You also need at least one model downloaded in Lemonade. Antar will not download one unless
you confirm it on the Models page. The
[local inference walkthrough](../phase1-local-inference.md) covers choosing models, chat,
vision, and benchmarks.

```bash
uv run antar backends
# lemonade   available        Connected. No model loaded.
```

If Lemonade is not running, the same command reports `unavailable` with the reason, and
everything else keeps working.

To point at a different server, or one protected by `LEMONADE_API_KEY`:

```bash
cp .env.example .env
# ANTAR_LEMONADE__BASE_URL=http://other-host:13305/v1
# ANTAR_LEMONADE__API_KEY=...
```

## Configuration file (optional)

```bash
cp configs/antar.example.yaml configs/antar.yaml   # git-ignored
```

Environment variables override the file. See `configs/` for an example of every typed spec.

## Docker (optional)

```bash
docker compose up
```

This builds the API image and runs the dashboard in a Node container. Lemonade stays on the
host and is reached through `host.docker.internal`.

## Troubleshooting

- **Dashboard says "Can't reach the Antar API".** Start the API, or set `ANTAR_API_URL`
  before `pnpm dev` if it is not on port 8080.
- **Lemonade shows "did not return JSON".** The URL is missing the `/v1` prefix or points
  at something else.
- **"is not downloaded".** Antar refuses to load or run a model whose weights are missing,
  because Lemonade would otherwise download it silently. Download it from the Models page.
- **The first reply is slow.** The model was not in memory, so the request included loading
  it. Load it first from the Models page, or expect this once.
- **Generation fails with a Lemonade error.** The message is passed through; an
  out-of-memory error means the model is too large for the free memory on this machine.
- **Lemonade shows 401.** The server has `LEMONADE_API_KEY` set; give Antar the same value
  in `ANTAR_LEMONADE__API_KEY`.
