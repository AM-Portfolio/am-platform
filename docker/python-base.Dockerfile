# Shared Python runtime for am-platform services (inlined in service Dockerfiles).
# am-parser pulls ghcr.io/am-portfolio/am-python-base; that requires org GHCR_TOKEN
# for cross-repo access. am-platform uses public python:3.12-slim to avoid 403 in CI.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
