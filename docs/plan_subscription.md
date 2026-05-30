# AM Subscription — Implementation Plan

## Background
The `am-subscription` service provides subscription lifecycle management as part of the `am-platform` monorepo.

## Repo Location
`am-platform/am-subscription`

## Tech Stack
Python 3.11+, FastAPI, SQLAlchemy (PostgreSQL), aiokafka, Keycloak JWT dependency.

## Responsibilities & Features (Fintech Tailored)
- **Granular Tier Management:** Manage subscription plans (Free, Pro, Premium, Institutional) tailored for fintech services (e.g., Live Market Data access, Algo-Trading capabilities, Higher rate limits).
- **Entitlements Engine (Feature Flags & Limits):** Real-time enforcement of entitlements such as daily API call quotas, maximum portfolio sizes, or access to advanced analytical instruments.
- **Metered Usage Tracking:** Track user usage against plan limits (e.g., number of documents parsed, trade signals generated) with support for hard stops or overage billing calculation.
- **Subscription State Machine:** Strict lifecycle tracking (Trial, Active, Past Due, Suspended, Paused, Cancelled) ensuring compliance and restricting trading/data access on suspension.
- **Audit Logging & Compliance:** Maintain an immutable ledger of all subscription state changes and plan upgrades/downgrades for regulatory/audit purposes.
- **Event Broadcasting:** Emit standard lifecycle events to Kafka (`am.subscription.created.v1`, `am.subscription.changed.v1`, `am.subscription.suspended.v1`, `am.usage.quota_exceeded.v1`) to immediately halt services in other domains (like terminating live websocket feeds in API Gateway).

## Fintech Specific Events (Kafka Triggers)
1. `am.usage.quota_exceeded.v1`: Emitted when an institution or user exceeds their API or data limits.
2. `am.subscription.suspended.v1`: Triggers immediate termination of active trading sessions and live market data websockets.
3. `am.subscription.renewed.v1`: Triggers restoration of limits and services.

## API Endpoints
```
GET    /subscriptions/plans                 — List all available fintech tiers & API limits
POST   /subscriptions                       — Create/Start trial subscription
GET    /subscriptions/me                    — Current user's subscription, active limits, and current usage
PATCH  /subscriptions/{id}/cancel           — Cancel subscription
PATCH  /subscriptions/{id}/pause            — Pause subscription (e.g., temporarily halting algo-trading features)
PATCH  /subscriptions/{id}/resume           — Resume paused subscription
PATCH  /subscriptions/{id}/upgrade          — Change plan (initiates prorated upgrade flow)
GET    /subscriptions/usage/history         — Historical usage metrics for billing/audit
POST   /subscriptions/internal/meter        — Internal API for other services to report usage (e.g., "100 API calls made")
GET    /subscriptions/entitlements/{userId} — Internal route for API Gateway to enforce real-time limits
```

## Gateway Enforcement Decision

Entitlement checks are enforced both at the gateway and inside downstream services.

Flow:

1. Gateway validates the access token through `am-platform-security`.
2. Gateway calls `am-subscription` for route-level entitlement decisions.
3. Gateway caches positive entitlement decisions for up to 60 seconds.
4. Downstream high-risk services re-check entitlements before regulated, expensive, or state-changing actions.
5. `am-subscription` records usage through an idempotent meter endpoint.

Internal enforcement endpoints:

```
GET  /subscriptions/internal/entitlements/{user_id}
POST /subscriptions/internal/check
POST /subscriptions/internal/meter
```

Required `POST /subscriptions/internal/check` payload:

```json
{
  "user_id": "keycloak_user_id",
  "tenant_id": "tenant_or_org_id",
  "feature": "live_market_data",
  "action": "stream.open",
  "quantity": 1,
  "idempotency_key": "request_or_business_key"
}
```

Failure behavior:

- Authentication failure: deny.
- Missing entitlement: deny.
- Quota exceeded: deny and emit `am.usage.quota_exceeded.v1`.
- Subscription service unavailable: fail closed for trading, live market data, paid analytics, and document parsing; fail open only for read-only account/profile views.

## State Machine

Allowed subscription states:

```text
trial -> active
trial -> expired
active -> past_due
active -> paused
active -> cancelled
past_due -> active
past_due -> suspended
paused -> active
suspended -> active
suspended -> cancelled
```

All state changes must append an audit record with `actor`, `reason`, `previous_state`, `next_state`, `correlation_id`, and timestamp.

---
## Infrastructure Reuse & Lago Integration (Enterprise Approach)
- **PostgreSQL & Redis:** We will reuse the existing PostgreSQL cluster in the `infra` namespace but create a **dedicated logical database** named `subscription` with a dedicated DB user (`am_subscription_user`). This follows the enterprise "one database per microservice" pattern.
- **Lago Billing Service:** Deploy with `npm run deploy:lago` (`automation/helm/deploy-lago.ps1` + `lago-values.yaml`). Internal DB/Redis are disabled; Lago connects to the `subscription` database and infra Redis.
- **Subscription database:** Provision with `npm run tf:billing:apply` (Terraform `automation/terraform/billing`, idempotent, no Helm destroy). 
- **Lago Components:**
  - `lago-api`: Core REST API for billing and subscriptions.
  - `lago-front`: Admin UI for managing plans and customers (Enabled as requested).
  - `lago-worker`: Background job processing (webhooks, invoice generation).
  - `lago-clock`: Scheduled task trigger (cron-like service).
- **Resource Limits (for ~10k Users):**
  - `lago-api`: Requests: `1 CPU, 2Gi RAM` | Limits: `2 CPU, 4Gi RAM`
  - `lago-front`: Requests: `0.5 CPU, 1Gi RAM` | Limits: `1 CPU, 2Gi RAM`
  - `lago-worker`: Requests: `1 CPU, 2Gi RAM` | Limits: `2 CPU, 4Gi RAM`
  - `lago-clock`: Requests: `0.2 CPU, 512Mi RAM` | Limits: `0.5 CPU, 1Gi RAM`
- **Keycloak Client:** Confidential client `am-lago-client` will be provisioned via Terraform for internal API calls.
- **Secrets:** DB passwords and client secrets will be stored in the git-ignored `.secrets.env` file.

---
## Core Services & Required Client IDs
| Service | Purpose | Keycloak Client (confidential) |
|---------|---------|--------------------------------|
| am-analysis | Data‑analysis microservice (statistical & ML models) | am-analysis-client |
| am-gateway | API gateway, token introspection, routing | am-gateway-client |
| am-market | Market‑data ingestion & business logic | am-market-client |
| am-market-data | Real‑time market feed provider | am-market-data-client |
| am-parser | Document parsing & enrichment | am-parser-client |
| am-doc-service-a | First doc service (PDF extraction) | am-doc-a-client |
| am-doc-service-b | Second doc service (OCR) | am-doc-b-client |
| am-doc-service-c | Third doc service (metadata indexing) | am-doc-c-client |

