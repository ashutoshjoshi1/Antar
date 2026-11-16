# Base install only: no PyTorch, no ROCm. Build from the repository root:
#   docker build -f apps/api/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY antar ./antar
COPY apps/api ./apps/api
COPY apps/cli ./apps/cli
RUN uv sync --frozen --no-dev

RUN useradd --create-home antar && mkdir -p /app/data && chown -R antar /app/data
USER antar

EXPOSE 8080
CMD ["/app/.venv/bin/antar", "serve", "--host", "0.0.0.0", "--port", "8080"]
