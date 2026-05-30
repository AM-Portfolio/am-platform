# AM Notification — build context: am-platform root (build_context: ..)
# Public Python base (see docker/python-base.Dockerfile). Avoids GHCR 403 on am-python-base.
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

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libraries/am-platform-common/ libraries/am-platform-common/
COPY libraries/am-platform-security/ libraries/am-platform-security/
RUN pip install --no-cache-dir ./libraries/am-platform-common ./libraries/am-platform-security

COPY am-notification/ am-notification/

ENV PYTHONPATH=/app/libraries/am-platform-common:/app/libraries/am-platform-security:/app/am-notification
ENV APP_ENV=production
ENV TZ=Asia/Kolkata
ENV APP_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=45s --retries=3 \
  CMD curl -f http://localhost:8080/health/live || exit 1

CMD ["uvicorn", "am_notification.main:app", "--host", "0.0.0.0", "--port", "8080"]
