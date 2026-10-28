#syntax=docker/dockerfile:1.7

# --- Base image pinned by digest so reproducible builds survive tag drift.
#     Refresh with `docker pull python:3.12-slim-bookworm` and paste the new sha.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

# --- Builder: install deps into a self-contained venv using uv.
FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY bot ./bot
COPY crawler ./crawler
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- Runtime: ffmpeg + the venv, nothing else.
FROM base AS runtime

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 1001 app \
 && useradd --system --uid 1001 --gid app --no-create-home --home-dir /app app \
 && mkdir -p /data \
 && chown app:app /data

WORKDIR /app
ENV PATH=/app/.venv/bin:${PATH} \
    PYTHONPATH=/app \
    MYINSTANTS_HEARTBEAT_FILE=/tmp/myinstants-heartbeat

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app bot ./bot
COPY --chown=app:app crawler ./crawler
COPY --chown=app:app pyproject.toml ./

USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=45s --retries=3 \
  CMD python -m bot.healthcheck || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "bot.run"]
