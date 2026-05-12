FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for psycopg (libpq) and curl for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
# Install with the [postgres] extra so prod has psycopg.
RUN pip install --upgrade pip && pip install ".[postgres]"

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Run Alembic migrations before starting the API. `cli_migrate` handles
# the one-time transition from create_all() to alembic-managed schemas.
CMD ["sh", "-c", "python -m src.cli_migrate && exec uvicorn src.main:app --host 0.0.0.0 --port 8000"]
