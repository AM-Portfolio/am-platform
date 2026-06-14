# AM AI Platform — Enterprise Development Plan
> **Version:** 2.0 | **Date:** June 2026 | **Status:** Final  
> **Principles:** Loosely Coupled · Low Latency · Observable · Safe · Scalable

---

## Design Goals

| Goal | Target |
|---|---|
| **Latency** | p50 < 800ms, p99 < 3s for LLM calls |
| **Coupling** | No service knows another's internal structure |
| **Availability** | Gateway stays up even if LLM API is down |
| **Safety** | All DB queries read-only, validated before execution |
| **Observability** | Every request traced end-to-end in Langfuse |
| **Scalability** | Each component scales independently |

---

## Architecture — Loosely Coupled Design

```
┌──────────────────────────────────────────────────────────────────┐
│                         AM Platform                              │
│                                                                  │
│  Client (Flutter/Service)                                        │
│       │                                                          │
│       ▼  HTTP/SSE (streaming)                                    │
│  ┌────────────────────────────────────────┐                      │
│  │         am-mcp-gateway  :8120          │                      │
│  │         (Python FastAPI)               │                      │
│  │                                        │                      │
│  │  ┌─────────┐  ┌──────────┐  ┌───────┐ │                      │
│  │  │ JWT     │  │  LLM     │  │ Cache │ │                      │
│  │  │ Auth    │  │ Router   │  │ Redis │ │                      │
│  │  └─────────┘  └──────────┘  └───────┘ │                      │
│  │       │            │                   │                      │
│  │       ▼            ▼ (async, streamed) │                      │
│  │  ┌──────────────────────────────────┐  │                      │
│  │  │      Langfuse + MLflow           │  │                      │
│  │  │      (non-blocking side-car)     │  │                      │
│  │  └──────────────────────────────────┘  │                      │
│  └──────────────┬──────────┬──────────────┘                      │
│                 │          │                                      │
│         Direct  │          │  Via Kafka (async tool results)     │
│         HTTP    │          │                                      │
│                 ▼          ▼                                      │
│  ┌──────────────────────────────────────┐                        │
│  │        am-mcp-server :8080           │                        │
│  │        (Java Spring AI)              │                        │
│  │                                      │                        │
│  │  PortfolioTools  MarketTools          │                        │
│  │  TradeTools      AnalysisTools        │                        │
│  │  AiAgentTools    UniversalDbTool 🆕   │                        │
│  └──────────────────────────────────────┘                        │
│                                                                  │
│  ┌──────────────────────────────────────┐                        │
│  │      am-ui-test-agent :8130          │  (Phase 3)             │
│  │      Playwright + Qwen-VL + Qdrant   │                        │
│  └──────────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘

LLM Fallback Chain (auto-failover):
  DeepSeek → Gemini → OpenAI
  (circuit breaker per provider)
```

---

## Latency Optimisation Strategy

### Problem: LLM calls are slow (1–30s)
### Solution: Stream everything + cache what you can

| Technique | Where | Latency saving |
|---|---|---|
| **SSE Streaming** | Gateway → Client | User sees first token in ~300ms instead of waiting 5s |
| **JWKS Cache** | Gateway security | -200ms (no Keycloak roundtrip per request) |
| **Response Cache** | Redis (repeated queries) | -100% latency on cache hit |
| **Prompt Cache** | DeepSeek supports it | -30% tokens billed, faster response |
| **Connection Pool** | LLM HTTP client | -50ms connection setup per request |
| **Async Observability** | Langfuse/MLflow fire-and-forget | -0ms added to hot path |
| **Parallel Tool Calls** | am-mcp-server | Run independent tools concurrently |
| **Keep-Alive** | LLM API connections | -100ms TLS handshake |

### Streaming Response Flow
```
Client                Gateway              DeepSeek API
  │                      │                      │
  │── POST /chat ────────►│                      │
  │                      │── POST (stream=true) ►│
  │                      │                      │
  │◄── SSE: token 1 ─────│◄── chunk 1 ──────────│
  │◄── SSE: token 2 ─────│◄── chunk 2 ──────────│
  │◄── SSE: token 3 ─────│◄── chunk 3 ──────────│
  │◄── SSE: [DONE] ───────│◄── [DONE] ───────────│
```
Client renders text as it arrives — no perceived wait.

### Caching Strategy
```
Request → Check Redis cache (TTL 5 min)
        → HIT:  return cached response (< 5ms)
        → MISS: call LLM, store result, return (1–10s)

Cache key: hash(user_id + message + model)
Do NOT cache: queries with "today", "now", "current price"
```

---

## Loose Coupling Strategy

### Problem: Tight coupling = one failure breaks everything
### Solution: Each component is independently deployable and replaceable

#### 1. Gateway ↔ MCP Server — Loose Contract
```
Gateway does NOT import any Java code.
Gateway calls am-mcp-server via HTTP REST:

POST http://am-mcp-server.am-apps-preprod.svc.cluster.local:8080/api/tools/execute
{
  "tool": "get_portfolio_summary",
  "arguments": { "userId": "user123" }
}

If am-mcp-server is DOWN → gateway returns LLM-only response (no tools)
Circuit breaker prevents cascade failure.
```

#### 2. LLM Provider — Swappable via env
```python
# Changing LLM = changing ONE env variable. No code change.
LLM_PROVIDER=deepseek   → DeepSeek API
LLM_PROVIDER=gemini     → Gemini API
LLM_PROVIDER=openai     → OpenAI API

# Auto-failover chain (configured in .env):
LLM_FALLBACK_CHAIN=deepseek,gemini,openai
```

#### 3. Observability — Fire and Forget
```python
# Langfuse and MLflow are NEVER on the hot path.
# They receive events via background async tasks.
# If Langfuse is down → request still succeeds.

asyncio.create_task(langfuse.log_trace(trace_data))   # non-blocking
asyncio.create_task(mlflow.log_run(run_data))          # non-blocking
```

#### 4. UniversalDbTool — Strategy Pattern (no coupling between DBs)
```java
// Each DB strategy is independent. Adding ClickHouse = add one class.
// Removing InfluxDB = delete one class. Nothing else changes.

interface DbQueryStrategy {
    boolean supports(DbType type);
    String generateQuery(String question, String database);
    List<Map<String, Object>> execute(String query, String database);
}
```

---

## Phase 1 — am-mcp-gateway

### Entry Criteria
- [ ] DeepSeek API key available in Vault
- [ ] Langfuse deployed and reachable at `langfuse.munish.org`
- [ ] `am-mcp-service` Keycloak client exists (already in am-platform .env.example)

### Exit Criteria (must pass before Phase 2 starts)
- [ ] `GET /health` returns 200
- [ ] `POST /api/v1/chat` with valid JWT returns streamed response
- [ ] Langfuse shows trace for every request
- [ ] MLflow shows run for every request  
- [ ] DeepSeek API down → Gemini fallback works
- [ ] Invalid JWT → 401 returned in < 50ms
- [ ] Load test: 50 concurrent users, p99 < 5s

### Complete File Structure
```
am-platform/
└── am-mcp-gateway/
    ├── .env.example              ← full env template
    ├── .env                      ← gitignored
    ├── .gitignore
    ├── Dockerfile                ← multi-stage build
    ├── Makefile                  ← make run|test|docker-build
    ├── requirements.txt
    ├── requirements-dev.txt
    ├── pyproject.toml
    │
    ├── app/
    │   ├── main.py               ← FastAPI app + lifespan
    │   ├── config.py             ← Pydantic BaseSettings
    │   │
    │   ├── security/
    │   │   ├── jwt_bearer.py     ← FastAPI Depends(JWTBearer())
    │   │   ├── jwks_cache.py     ← LRU cache, 5-min TTL
    │   │   └── models.py         ← TokenPayload dataclass
    │   │
    │   ├── llm/
    │   │   ├── base.py           ← Abstract: chat() + stream()
    │   │   ├── deepseek.py       ← DEFAULT — httpx async + SSE
    │   │   ├── gemini.py         ← fallback 1
    │   │   ├── openai.py         ← fallback 2
    │   │   ├── factory.py        ← reads env, returns provider chain
    │   │   └── circuit_breaker.py ← per-provider circuit breaker
    │   │
    │   ├── cache/
    │   │   ├── response_cache.py ← Redis get/set with TTL
    │   │   └── key_builder.py    ← deterministic cache key
    │   │
    │   ├── observability/
    │   │   ├── langfuse_tracer.py ← async, non-blocking
    │   │   └── mlflow_tracker.py  ← async, non-blocking
    │   │
    │   ├── api/
    │   │   ├── chat_router.py    ← POST /api/v1/chat (SSE stream)
    │   │   ├── health_router.py  ← GET /health, /ready
    │   │   └── router.py
    │   │
    │   ├── schemas/
    │   │   ├── chat.py           ← ChatRequest, ChatResponse, StreamChunk
    │   │   └── errors.py         ← ErrorResponse, GatewayError
    │   │
    │   ├── session/
    │   │   └── store.py          ← Redis session (fallback: in-memory)
    │   │
    │   └── middleware/
    │       ├── logging.py        ← structlog + trace_id injection
    │       └── rate_limiter.py   ← per-user rate limit (Redis)
    │
    └── tests/
        ├── conftest.py
        ├── test_chat_stream.py   ← SSE streaming test
        ├── test_security.py      ← JWT valid/invalid/expired
        ├── test_fallback.py      ← DeepSeek down → Gemini
        └── test_cache.py         ← cache hit/miss
```

### Environment Variables (`.env.example`)
```env
# ── Service ────────────────────────────────────────────────
APP_PORT=8120
APP_ENV=development
LOG_LEVEL=INFO
LOG_FORMAT=text                    # text (dev) | json (prod)

# ── Security ───────────────────────────────────────────────
OIDC_JWKS_URL=http://auth.munish.org/auth/realms/am-realm/protocol/openid-connect/certs
OIDC_ISSUER=http://auth.munish.org/auth/realms/am-realm
OIDC_JWKS_CACHE_TTL_SECONDS=300   # 5 min — reduces Keycloak calls
AM_MCP_CLIENT_ID=am-mcp-service
AM_MCP_CLIENT_SECRET=<get-from-vault>

# ── LLM Provider ───────────────────────────────────────────
# Primary + automatic failover chain
LLM_PROVIDER=deepseek
LLM_FALLBACK_CHAIN=deepseek,gemini,openai   # left = highest priority
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=4096
LLM_TIMEOUT_SECONDS=60
LLM_STREAM=true                    # stream response by default

# Circuit breaker (per provider)
LLM_CB_FAILURE_THRESHOLD=5         # open after 5 consecutive failures
LLM_CB_RECOVERY_TIMEOUT_SECONDS=30 # try again after 30s

# API Keys
DEEPSEEK_API_KEY=<get-from-vault>
GOOGLE_API_KEY=<get-from-vault>
OPENAI_API_KEY=<get-from-vault>

# ── Caching ────────────────────────────────────────────────
CACHE_ENABLED=true
CACHE_BACKEND=redis                # redis | memory
CACHE_TTL_SECONDS=300              # 5 min default
REDIS_URL=redis://:password@redis.infra.svc.cluster.local:6379/4

# ── am-mcp-server (tool execution) ─────────────────────────
MCP_SERVER_URL=http://am-mcp-server.am-apps-preprod.svc.cluster.local:8080
MCP_SERVER_TIMEOUT_SECONDS=20
MCP_SERVER_ENABLED=true            # false = LLM-only mode (no tools)

# ── Observability — async, never blocks requests ────────────
LANGFUSE_ENABLED=true
LANGFUSE_HOST=https://langfuse.munish.org
LANGFUSE_PUBLIC_KEY=<get-from-vault>
LANGFUSE_SECRET_KEY=<get-from-vault>
LANGFUSE_FLUSH_INTERVAL_SECONDS=5  # batch send traces

MLFLOW_ENABLED=true
MLFLOW_TRACKING_URI=http://mlflow.am-ai.svc.cluster.local:5000
MLFLOW_EXPERIMENT_NAME=am-mcp-gateway
MLFLOW_ASYNC=true                  # always fire-and-forget

# ── Rate Limiting ──────────────────────────────────────────
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60  # per user
RATE_LIMIT_BURST=10

# ── Session ────────────────────────────────────────────────
SESSION_BACKEND=redis
SESSION_TTL_SECONDS=3600

# ── CORS ──────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:9007,https://am.munish.org,https://am.asrax.in
```

### API Endpoints
| Method | Path | Auth | Mode | Description |
|---|---|---|---|---|
| `POST` | `/api/v1/chat` | JWT | Stream (SSE) | Main chat — streams response |
| `POST` | `/api/v1/chat/sync` | JWT | Sync | Chat — wait for full response |
| `GET` | `/api/v1/providers` | JWT | — | List LLM providers + status |
| `DELETE` | `/api/v1/cache` | JWT | — | Flush user's cache |
| `GET` | `/health` | Public | — | Liveness probe |
| `GET` | `/ready` | Public | — | Readiness probe |
| `GET` | `/metrics` | Internal | — | Prometheus metrics |

### Error Handling
```
LLM Timeout (>60s)        → 504 Gateway Timeout
All providers down         → 503 Service Unavailable + cached hint
Invalid JWT               → 401 Unauthorized (< 50ms, no LLM call)
JWT expired               → 401 with "token_expired" error code
Rate limit exceeded        → 429 Too Many Requests + retry-after header
MCP server down           → 200 with LLM-only response (graceful degrade)
Cache error               → log warning, continue without cache (never fail)
Langfuse/MLflow error     → log warning, continue (never affect request)
```

### Task List — Phase 1
**Prerequisites**
- [ ] Langfuse deployed (`langfuse.munish.org` reachable)
- [ ] MLflow deployed (`mlflow.am-ai.svc.cluster.local:5000` reachable)
- [ ] DeepSeek API key added to Vault + am-platform secrets

**Core**
- [ ] Directory structure + `.gitignore`
- [ ] `requirements.txt` + `requirements-dev.txt` + `pyproject.toml`
- [ ] `.env.example` with all variables
- [ ] `app/config.py` — Pydantic BaseSettings, singleton
- [ ] `app/main.py` — FastAPI app factory + lifespan (startup checks)

**Security**
- [ ] `app/security/jwks_cache.py` — JWKS fetch + LRU cache (5-min TTL)
- [ ] `app/security/jwt_bearer.py` — FastAPI Depends, validates in < 5ms
- [ ] `app/security/models.py` — TokenPayload, UserClaims

**LLM Layer**
- [ ] `app/llm/base.py` — `chat()` + `stream()` abstract methods
- [ ] `app/llm/deepseek.py` — httpx async, SSE streaming
- [ ] `app/llm/gemini.py` — google-genai SDK, SSE
- [ ] `app/llm/openai.py` — openai SDK, SSE
- [ ] `app/llm/factory.py` — reads `LLM_FALLBACK_CHAIN`, returns provider list
- [ ] `app/llm/circuit_breaker.py` — per-provider open/close/half-open

**Caching**
- [ ] `app/cache/response_cache.py` — Redis get/set, TTL, serialization
- [ ] `app/cache/key_builder.py` — deterministic key, excludes time-sensitive queries

**Observability (async)**
- [ ] `app/observability/langfuse_tracer.py` — `asyncio.create_task()` based
- [ ] `app/observability/mlflow_tracker.py` — `asyncio.create_task()` based

**API**
- [ ] `app/schemas/chat.py` — ChatRequest, ChatResponse, StreamChunk, ErrorResponse
- [ ] `app/api/chat_router.py` — SSE streaming + sync endpoints
- [ ] `app/api/health_router.py` — liveness + readiness checks
- [ ] `app/api/router.py` — mount all routers
- [ ] `app/middleware/logging.py` — structlog + trace_id
- [ ] `app/middleware/rate_limiter.py` — Redis sliding window
- [ ] `app/session/store.py` — Redis session, in-memory fallback

**Infrastructure**
- [ ] `Dockerfile` — multi-stage, non-root user
- [ ] `Makefile` — `run`, `test`, `docker-build`, `lint`
- [ ] Helm chart — `am-platform/helm/am-mcp-gateway/`
- [ ] Traefik route in `am-infra/traefik/apps.yaml`

**Tests**
- [ ] `tests/conftest.py` — mock LLM provider + Redis
- [ ] `tests/test_chat_stream.py` — SSE streaming assertions
- [ ] `tests/test_security.py` — valid/expired/missing JWT
- [ ] `tests/test_fallback.py` — circuit breaker + provider fallover
- [ ] `tests/test_cache.py` — hit, miss, TTL expiry
- [ ] `tests/test_rate_limiter.py`

---

## Phase 2 — UniversalDbTool (Java, am-mcp-server)

### Design — Strategy Pattern
```java
// Router — selects strategy by dbType
@Tool(name = "query_database")
public String queryDatabase(String dbType, String database, String question) {
    DbQueryStrategy strategy = registry.getStrategy(DbType.from(dbType));
    String query = strategy.generateQuery(question, database);      // LLM generates
    query = strategy.validate(query);                               // safety check
    List<Map<String,Object>> results = strategy.execute(query, database);
    return ResponseHelper.toJson(Map.of(
        "query", query,      // always return generated query for audit
        "results", results,
        "count", results.size()
    ));
}
```

### Query Safety Enforcement (per DB)
| DB | Safety Rule |
|---|---|
| PostgreSQL | Parse SQL AST → reject if not SELECT. Reject `INFORMATION_SCHEMA` access. |
| MongoDB | Reject `$where`, `$function`. Cap `$limit` to 50 if not set. |
| InfluxDB | Enforce time window ≤ 7 days. Read-only Flux queries only. |
| Redis | Allow: GET, HGET, KEYS, LRANGE, SMEMBERS, TTL. Block: SET, DEL, FLUSHDB. |

### File Structure (additions to am-mcp-server)
```
am-core-services/services/am-mcp-server/src/main/java/com/am/mcp/
├── tools/
│   ├── UniversalDbTool.java              ← @Tool entry point
│   └── db/
│       ├── DbType.java                   ← enum: MONGODB, POSTGRESQL, INFLUXDB, REDIS
│       ├── DbQueryStrategy.java          ← interface
│       ├── DbStrategyRegistry.java       ← Spring: finds all strategies by type
│       ├── QuerySafetyValidator.java     ← per-type safety checks
│       ├── strategies/
│       │   ├── MongoDbStrategy.java      ← Spring Data Mongo (already connected)
│       │   ├── PostgresStrategy.java     ← JdbcTemplate, read-only datasource
│       │   ├── InfluxDbStrategy.java     ← InfluxDB Java client
│       │   └── RedisStrategy.java        ← Lettuce, command allowlist
│       └── model/
│           └── QueryResult.java          ← query + results + metadata
└── config/
    └── UniversalDbConfig.java            ← @ConditionalOnProperty beans per DB
```

### Task List — Phase 2
**Entry criteria:** Phase 1 exit criteria all green.

- [ ] `DbType.java` enum + `DbQueryStrategy.java` interface
- [ ] `DbStrategyRegistry.java` — Spring collects all strategies
- [ ] `QuerySafetyValidator.java` — SQL AST parser, Mongo allowlist
- [ ] `MongoDbStrategy.java` — uses existing Spring Data Mongo bean
- [ ] `PostgresStrategy.java` — read-only DataSource bean
- [ ] `InfluxDbStrategy.java` — InfluxDB client + Flux query gen
- [ ] `RedisStrategy.java` — Lettuce, allowlisted commands only
- [ ] `UniversalDbConfig.java` — conditional beans, env-toggled
- [ ] `UniversalDbTool.java` — @Tool, calls registry + validator
- [ ] `application.yaml` — add per-DB enable flags
- [ ] `pom.xml` — add InfluxDB client dependency
- [ ] Unit tests — each strategy with mocked driver
- [ ] Safety tests — SQL injection, Mongo $where, Redis FLUSHDB all rejected
- [ ] Integration test — NL → query → result, end-to-end

---

## Phase 3 — am-ui-test-agent

### Entry Criteria
- [ ] Phase 1 + Phase 2 exit criteria all green
- [ ] Qdrant deployed in K8s
- [ ] Test user account created in Keycloak (`test-agent@munish.org`)
- [ ] `TOGETHER_API_KEY` added to Vault (for Qwen2.5-VL vision model via Together AI API)

### Design — LangGraph Agent
```
TRIGGER: POST /api/v1/test/run
  │
  ▼
PLAN node (DeepSeek)
  → reads test spec + Qdrant memory
  → generates ordered step list
  │
  ▼
EXECUTE node (loop)
  → Playwright performs action
  → Screenshot captured
  → Qwen2.5-VL describes what it sees
  → Assert pass/fail
  → If fail: SELF-HEAL node
      → Vision finds element by appearance
      → Store new selector in Qdrant
      → Retry step
  │
  ▼
REPORT node
  → HTML report with screenshots
  → Bug list with reproduction steps
  → Langfuse trace link
  → Store in MongoDB
```

### Task List — Phase 3
**Entry criteria:** Phase 1 + 2 exit criteria all green.

**Scaffold**
- [ ] New repo `am-ui-test-agent`
- [ ] `.env.example`, `requirements.txt`, `pyproject.toml`
- [ ] `Dockerfile` + Helm chart

**Browser**
- [ ] `app/browser/controller.py` — Playwright async, headed/headless toggle
- [ ] `app/browser/screenshot.py` — capture, resize, base64 encode
- [ ] `app/browser/dom_extractor.py` — extract all interactive elements

**Vision**
- [ ] `app/vision/analyzer.py` — Qwen2.5-VL via API: describe screenshot
- [ ] `app/vision/element_detector.py` — find button/input by description
- [ ] `app/vision/diff_detector.py` — pixel diff + semantic diff

**Memory (Qdrant)**
- [ ] `app/memory/qdrant_client.py` — connection + collection management
- [ ] `app/memory/ui_memory.py` — store page states + selectors
- [ ] `app/memory/test_memory.py` — store past runs + outcomes
- [ ] `app/memory/embedder.py` — text embeddings (DeepSeek) + image (CLIP)

**Tools**
- [ ] `app/tools/navigate_tool.py` — go_to_url, click, type, scroll, wait
- [ ] `app/tools/assert_tool.py` — assert_text, assert_url, assert_visible
- [ ] `app/tools/auth_tool.py` — login via Keycloak (reusable across tests)
- [ ] `app/tools/screenshot_tool.py` — take + compare + diff

**Agent**
- [ ] `app/agent/planner.py` — DeepSeek: spec → step list
- [ ] `app/agent/executor.py` — step runner + self-heal logic
- [ ] `app/agent/reporter.py` — aggregate results → bug list
- [ ] `app/agent/test_agent.py` — LangGraph graph wiring all nodes

**API + Scheduler**
- [ ] `app/api/test_router.py` — POST /api/v1/test/run
- [ ] `app/api/report_router.py` — GET /api/v1/test/reports
- [ ] `app/api/webhook_router.py` — POST /api/v1/webhooks/deploy (CI/CD trigger)
- [ ] `app/scheduler/cron_runner.py` — nightly regression at 2am
- [ ] `app/reporting/html_reporter.py` — rich HTML with screenshots
- [ ] `app/reporting/storage.py` — persist to MongoDB

**Observability**
- [ ] `app/observability/langfuse_tracer.py` — trace every test step
- [ ] `app/observability/mlflow_tracker.py` — pass rate, coverage, duration

**Tests**
- [ ] `tests/test_browser_controller.py`
- [ ] `tests/test_vision_analyzer.py`
- [ ] `tests/test_qdrant_memory.py`
- [ ] `tests/test_self_healing.py`

---

## Shared Infrastructure

### Services to Deploy (Terraform + Helm in am-infra)
| Service | Component | Hosting / API Type | Est. Cost |
|---|---|---|---|
| Text LLM | **DeepSeek V3** | External API | ~$0.14/M tokens |
| Vision LLM | **Qwen2.5-VL** | Together AI API | ~$0.20/M tokens |
| Vector Store | **Qdrant** | Self-hosted K8s | Free |
| Deep Tracing | **Langfuse** | Self-hosted K8s | Free |
| Basic Tracking | **MLflow** | Self-hosted K8s | Free |
| Browser Control | **Playwright** | Runs in agent pod | Free |

**Total LLM cost estimate:** < $10/month for all AI operations  
**No GPU node required** — all models served via external APIs. Set `TOGETHER_API_KEY` in Vault.

### Traefik Routes (am-infra/traefik/apps.yaml)
```yaml
# New routes to add:
am-mcp-gateway:
  rule: Host(`am.munish.org`) && PathPrefix(`/mcp`)
  service: am-mcp-gateway:8120
  middlewares: [forward-auth]

am-ui-test-agent:
  rule: Host(`am.munish.org`) && PathPrefix(`/ui-test`)
  service: am-ui-test-agent:8130
  middlewares: [forward-auth]

langfuse:
  rule: Host(`langfuse.munish.org`)
  service: langfuse.am-ai:3000
```

### Port Registry (All Services)
| Service | Internal Port | Namespace |
|---|---|---|
| `am-mcp-gateway` | `8120` | `am-apps-preprod` |
| `am-ui-test-agent` | `8130` | `am-apps-preprod` |
| Langfuse | `3000` | `am-ai` |
| MLflow | `5000` | `am-ai` |
| Qdrant | `6333` | `am-ai` |

> Qwen2.5-VL (vision) is called via Together AI external API — no internal port needed.

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| DeepSeek API unavailable | Medium | High | Auto-failover to Gemini → OpenAI |
| LLM generates unsafe DB query | Low | Critical | Validate before execution, read-only user |
| Langfuse down during request | Low | Low | Async, fire-and-forget, never blocks |
| am-mcp-server down | Medium | Medium | Gateway serves LLM-only response |
| Qwen-VL hallucination | Medium | Medium | Validate with DOM assertion after vision |
| Rate limit exceeded on LLM API | Medium | Medium | Redis rate limiter + queue overflow |

---

## Timeline

```
Week 1: Infrastructure
  └── Deploy Langfuse + MLflow to K8s
  └── Configure Vault secrets (DeepSeek key etc.)

Week 2: Phase 1 — am-mcp-gateway
  └── Core service, LLM routing, JWT, streaming
  └── Caching, rate limiting, observability
  └── Tests passing, deployed to preprod

Week 3: Phase 2 — UniversalDbTool
  └── Strategy pattern + all 4 DB types
  └── Safety validation for each
  └── Tests + integration

Week 4-6: Phase 3 — am-ui-test-agent
  └── Week 4: browser + vision + memory
  └── Week 5: agent (plan → execute → report)
  └── Week 6: scheduler + CI/CD webhook + full coverage
```
