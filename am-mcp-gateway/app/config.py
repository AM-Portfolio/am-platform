import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=os.getenv("ENV_FILE_PATH", ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ── Service ────────────────────────────────────────────────
    APP_PORT: int = Field(default=8120)
    APP_ENV: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    LOG_FORMAT: str = Field(default="text")  # text | json

    # ── Security ───────────────────────────────────────────────
    OIDC_JWKS_URL: str = Field(default="http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/certs")
    OIDC_ISSUER: str = Field(default="http://auth.munish.org/auth/realms/am-realm")
    OIDC_JWKS_CACHE_TTL_SECONDS: int = Field(default=300)
    AM_MCP_CLIENT_ID: str = Field(default="am-mcp-service")
    AM_MCP_CLIENT_SECRET: Optional[str] = Field(default=None)

    # ── LLM Provider ───────────────────────────────────────────
    LLM_PROVIDER: str = Field(default="litellm")          # litellm | deepseek | gemini | openai
    LLM_FALLBACK_CHAIN: str = Field(default="litellm,deepseek,gemini")
    LLM_MODEL: str = Field(default="deepseek/deepseek-chat")  # LiteLLM model name format
    LLM_TEMPERATURE: float = Field(default=0.2)
    LLM_MAX_TOKENS: int = Field(default=4096)
    LLM_TIMEOUT_SECONDS: int = Field(default=60)
    LLM_STREAM: bool = Field(default=True)

    # LiteLLM Proxy (internal cluster URL)
    LITELLM_BASE_URL: str = Field(default="http://litellm.am-ai.svc.cluster.local:4000")
    LITELLM_MASTER_KEY: Optional[str] = Field(default=None)  # sk-... key injected via secret

    # Circuit Breaker Configuration
    LLM_CB_FAILURE_THRESHOLD: int = Field(default=5)
    LLM_CB_RECOVERY_TIMEOUT_SECONDS: int = Field(default=30)

    # API Keys
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None)
    GOOGLE_API_KEY: Optional[str] = Field(default=None)
    OPENAI_API_KEY: Optional[str] = Field(default=None)

    # ── Caching ────────────────────────────────────────────────
    CACHE_ENABLED: bool = Field(default=True)
    CACHE_BACKEND: str = Field(default="redis")  # redis | memory
    CACHE_TTL_SECONDS: int = Field(default=300)
    REDIS_URL: str = Field(default="redis://localhost:6379/4")

    # ── am-mcp-server (tool execution) ─────────────────────────
    MCP_SERVER_URL: str = Field(default="http://localhost:8080")
    MCP_SERVER_TIMEOUT_SECONDS: int = Field(default=20)
    MCP_SERVER_ENABLED: bool = Field(default=True)

    # ── Observability ──────────────────────────────────────────
    LANGFUSE_ENABLED: bool = Field(default=False)
    LANGFUSE_HOST: str = Field(default="https://langfuse.munish.org")
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(default=None)
    LANGFUSE_SECRET_KEY: Optional[str] = Field(default=None)
    LANGFUSE_FLUSH_INTERVAL_SECONDS: int = Field(default=5)

    MLFLOW_ENABLED: bool = Field(default=False)
    MLFLOW_TRACKING_URI: Optional[str] = Field(default=None)
    MLFLOW_EXPERIMENT_NAME: str = Field(default="am-mcp-gateway")
    MLFLOW_ASYNC: bool = Field(default=True)

    # ── Rate Limiting ──────────────────────────────────────────
    RATE_LIMIT_ENABLED: bool = Field(default=True)
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=60)
    RATE_LIMIT_BURST: int = Field(default=10)

    # ── Session ────────────────────────────────────────────────
    SESSION_BACKEND: str = Field(default="redis")
    SESSION_TTL_SECONDS: int = Field(default=3600)

    # ── CORS ──────────────────────────────────────────────────
    CORS_ORIGINS: str = Field(default="*")

    @property
    def fallback_chain_list(self) -> List[str]:
        return [p.strip() for p in self.LLM_FALLBACK_CHAIN.split(",") if p.strip()]

settings = Settings()
