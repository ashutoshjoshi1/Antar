.PHONY: install api web check check-api check-web format

install:
	uv sync
	cd apps/web && pnpm install

api:
	uv run antar serve --reload

web:
	cd apps/web && pnpm dev

format:
	uv run ruff format .
	uv run ruff check . --fix

check-api:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy
	uv run pytest --cov --cov-fail-under=80

check-web:
	cd apps/web && pnpm typecheck && pnpm lint && pnpm test && pnpm build

# Everything CI runs.
check: check-api check-web
