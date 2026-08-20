FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY am_mcp_hub ./am_mcp_hub
COPY migrations ./migrations
COPY admin-ui ./admin-ui
COPY samples ./samples
RUN pip install --no-cache-dir .
ENV APP_PORT=8130
ENV LOCAL_CREDS_DIR=/local-creds
EXPOSE 8130
CMD ["uvicorn", "am_mcp_hub.main:app", "--host", "0.0.0.0", "--port", "8130"]
