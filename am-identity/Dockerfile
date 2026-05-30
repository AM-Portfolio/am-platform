# AM Identity — build context: am-platform root (build_context: ..)
ARG BASE_REGISTRY=""
FROM ${BASE_REGISTRY}am-python-base:latest

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY libraries/am-platform-common/ libraries/am-platform-common/
COPY libraries/am-platform-security/ libraries/am-platform-security/
RUN pip install --no-cache-dir ./libraries/am-platform-common ./libraries/am-platform-security

COPY am-identity/ am-identity/

ENV PYTHONPATH=/app/libraries/am-platform-common:/app/libraries/am-platform-security:/app/am-identity
ENV APP_ENV=production
ENV TZ=Asia/Kolkata

ENV APP_PORT=8080

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

CMD ["uvicorn", "am_identity.main:app", "--host", "0.0.0.0", "--port", "8080"]
