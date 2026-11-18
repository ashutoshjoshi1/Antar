# Developer guide

## Setup

```bash
make install     # uv sync + pnpm install
make api         # terminal 1 — API with reload on :8080
make web         # terminal 2 — dashboard on :5173
```

See [local installation](../installation/local.md) for prerequisites.

## Before you push

```bash
make check
```

This runs exactly what CI runs: `ruff format --check`, `ruff check`, `mypy` (strict),
`pytest` with an 80% coverage floor, then `tsc`, ESLint, Vitest, and a production build of
the dashboard.

## Where things go

| You are adding… | Put it in… |
|---|---|
| A new inference engine | `antar/backends/<name>/`, registered in `backends/registry.py` |
| A metric | `antar/modalities/catalog.py` |
| A benchmark workload | `antar/benchmarking/workloads.py` (bump `version` when prompts change) |
| An inference option | `antar/inference/types.py`, after confirming the backend documents it |
| A technique or its applicability | `antar/optimization/job.py` |
| A setting | `antar/config/settings.py`, `.env.example`, `configs/antar.example.yaml` |
| An endpoint | `apps/api/antar_api/routes.py` + `schemas.py`, then `apps/web/src/lib/types.ts` |
| A dashboard page | `apps/web/src/pages/`, routed in `src/App.tsx`, linked in `AppShell.tsx` |

Read [the architecture overview](../architecture/overview.md) first; the backend contract
there is the part most contributions touch.

## Testing

- **Backend.** `tests/unit` for library behaviour, `tests/integration` for the API through
  the real app factory. Tests never use the network: Lemonade is stubbed with
  `httpx.MockTransport` (see `tests/conftest.py`). The `settings` fixture isolates tests
  from your environment, `.env`, and YAML.
- **Frontend.** Vitest with Testing Library. Pure logic (`format.ts`, filters, job preview)
  is unit tested; `App.test.tsx` renders routes against a stubbed `fetch`.
- Test the failure path. For a backend that means "what does the user see when it is down".
- Fixtures that look like upstream responses should be trimmed from the upstream
  documentation, with the source noted.

Live tests run real inference against your Lemonade server. They are excluded by default,
skip themselves when no suitable model is downloaded, and never download anything:

```bash
uv run pytest -m lemonade_live -v
```

The cloud path has its own opt-in tests against a real vLLM endpoint on an AMD GPU host.
They use whatever `ANTAR_CLOUD__BASE_URL` points at, send a few short requests to a server
that is already running, and start and stop nothing. They use paid instance time, so run
them only when you are authorized to:

```bash
uv run pytest -m amd_live -s
```

In ordinary tests, vLLM is an `httpx.MockTransport` (`FakeVllm` in `tests/conftest.py`) and
SSH is a `RemoteRunner` fake (`FakeRunner`). The `amd-smi` documents in the tests are
synthetic and say so.

Say which live tests you ran, and on what hardware, in the pull request. A skipped live
test is not a passed one.

## Working with external APIs

Before writing or changing an adapter, read the current official documentation and note in
the module docstring what you checked, against which version, and when. Lemonade in
particular moves quickly: its default port and its documented URL prefix have both changed
over time.

## Honesty rules

These are enforced in review:

- No number appears in the repository unless a recorded experiment produced it.
- Simulated output is flagged `simulated=True` end to end.
- A capability is `supported` only if a test exercises it.
- Unfinished UI says "Not built yet".

## Commits and pull requests

Conventional commit prefixes (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`).
Keep pull requests to one concern and fill in the template, including links to any upstream
documentation you relied on.
