#syntax=docker/dockerfile:1

FROM dhi.io/python:3.13-dev

COPY --from=ghcr.io/astral-sh/uv:0.9.24 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock /app/
COPY sdks/python /app/sdks/python/
COPY honcho-cli /app/honcho-cli/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

ENV PATH="/app/.venv/bin:$PATH"
ENV HOME=/app
ENV UV_CACHE_DIR=/tmp/uv-cache

COPY src/ /app/src/
COPY migrations/ /app/migrations/
COPY scripts/ /app/scripts/
COPY docker/ /app/docker/
COPY alembic.ini /app/alembic.ini
COPY config.toml* /app/

EXPOSE 8000

CMD ["fastapi", "run", "--host", "0.0.0.0", "src/main.py"]
