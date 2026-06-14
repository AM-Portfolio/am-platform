# AM MCP Gateway

The Gateway routes MCP and LLM queries through local and remote models, ensuring secure, fast, and structured execution.

## 🔒 Secret Management & Security Guidelines

To prevent sensitive credentials and API keys from leaking, the gateway strictly decouples credentials from code and configuration:

### 1. In-Cluster (Preprod / Production)
In cluster environments, secrets are injected dynamically using **HashiCorp Vault Agent Sidecars**.
- Secrets are mapped via [vault-mappings.yaml](file:///a:/InfraCode/AM-Portfolio-grp/am-platform/am-mcp-gateway/helm/vault-mappings.yaml).
- The Vault agent writes secrets to memory-mounted files under `/vault/secrets/`.
- Sourced files automatically set environment variables (such as `TOGETHER_API_KEY`, `LITELLM_MASTER_KEY`, etc.) inside the shell before running the Gateway process:
  ```bash
  . /vault/secrets/identity-oidc 2>/dev/null || true
  . /vault/secrets/llm-api-keys 2>/dev/null || true
  . /vault/secrets/observability 2>/dev/null || true
  . /vault/secrets/redis 2>/dev/null || true
  exec uvicorn app.main:app
  ```

### 2. Local Development
For local testing:
- Create a `.env` file in the root of `am-mcp-gateway` (or use the global `am-platform/.secrets.env`).
- Secrets will be parsed automatically at startup by Pydantic settings.
- **Never commit `.env` or `.secrets.env` files.** The global and local `.gitignore` rules are configured to prevent these files from being tracked by Git.

### 3. Golden Rule
> [!IMPORTANT]
> **Never hardcode or place real API keys/credentials inside values files (like `values.yaml` or `values.preprod.yaml`).**
> All credential integrations must be mapped via Vault paths and key bindings.
