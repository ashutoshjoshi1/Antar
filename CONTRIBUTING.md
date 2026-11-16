# Contributing to Antar

Thanks for your interest. Antar is at an early stage, which makes this a good time to shape
it — and a time when a few rules matter a lot.

## Ground rules

1. **No unmeasured claims.** Do not add benchmark numbers, speedups, or quality statements
   that a recorded experiment did not produce. This applies to code, docs, the UI, and PR
   descriptions.
2. **No overstated support.** A capability is `supported` only when Antar can execute it
   and a test proves it. Unfinished features are labelled as such.
3. **No secrets or weights.** Never commit credentials, private keys, `.env`, or model
   files.
4. **Check upstream docs.** When you integrate with an external API, link the official
   documentation you verified it against.
5. **No surprise cloud cost.** Nothing may start a paid resource without an explicit user
   action.

## Getting started

```bash
make install
make check      # must pass before you open a pull request
```

The [developer guide](docs/developer-guide/setup.md) explains the layout, testing approach,
and where new code belongs. The [architecture overview](docs/architecture/overview.md)
describes the backend contract. The [roadmap](docs/ROADMAP.md) shows what is planned; the
next milestone is the best place to help.

## Pull requests

- Open an issue first for anything larger than a small fix, so the approach can be agreed.
- One concern per pull request. Keep diffs focused; do not reformat unrelated code.
- Add or update tests for behaviour you change, including the failure path.
- Update docs when an interface, config key, or architectural boundary changes.
- Use conventional commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.

## Code style

- Python: typed, `ruff format`, `ruff check`, `mypy --strict`. Pydantic models are frozen.
- TypeScript: strict mode, ESLint, no `any`. Server state through the hooks in
  `apps/web/src/lib/api.ts`.
- Prefer a small working slice over a general abstraction for a future need.

## Reporting bugs and security issues

Use the issue templates for bugs and feature requests. Report vulnerabilities privately as
described in [SECURITY.md](SECURITY.md).

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
