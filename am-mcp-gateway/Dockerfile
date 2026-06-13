# AM MCP Gateway — build context: am-platform root (build_context: ..)
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

# Copy root requirements first to cache base platform dependencies
COPY requirements.txt ./requirements-platform.txt
RUN pip install --no-cache-dir -r requirements-platform.txt

# Copy gateway-specific requirements and install them
COPY am-mcp-gateway/requirements.txt ./am-mcp-gateway/requirements.txt
RUN pip install --no-cache-dir -r am-mcp-gateway/requirements.txt

# Copy shared libraries
COPY libraries/am-platform-common/ libraries/am-platform-common/
COPY libraries/am-platform-security/ libraries/am-platform-security/
RUN pip install --no-cache-dir ./libraries/am-platform-common ./libraries/am-platform-security

# Copy service code
COPY am-mcp-gateway/ am-mcp-gateway/

# Set environment
ENV PYTHONPATH=/app/libraries/am-platform-common:/app/libraries/am-platform-security:/app/am-mcp-gateway
ENV APP_ENV=production
ENV TZ=Asia/Kolkata
ENV APP_PORT=8120

EXPOSE 8120

HEALTHCHECK --interval=30s --timeout=3s --start-period=45s --retries=3 \
  CMD curl -f http://localhost:8120/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8120"]

