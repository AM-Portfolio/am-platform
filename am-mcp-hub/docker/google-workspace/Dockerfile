FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
  && rm -rf /var/lib/apt/lists/* \
  && pip install --no-cache-dir "workspace-mcp==1.23.1"

ENV PORT=8000
ENV WORKSPACE_MCP_PORT=8000
# Required so published ports work from the host / other containers
ENV WORKSPACE_MCP_HOST=0.0.0.0
ENV MCP_ENABLE_OAUTH21=false
ENV OAUTHLIB_INSECURE_TRANSPORT=1

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=8s --start-period=40s --retries=5 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# tool-tier core keeps the surface smaller for local Inspector
CMD ["sh", "-c", "workspace-mcp --transport streamable-http --tool-tier ${TOOL_TIER:-core}"]
