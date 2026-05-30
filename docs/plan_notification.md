# AM Notification — Implementation Plan

## Background

The `am-notification` service is a **lean orchestration layer** for multi-channel notification delivery. It owns platform-specific concerns (Kafka ingestion, dedupe, preferences, audit, DLQ) and delegates **channel delivery, workflow execution, and in-app feed storage** to **[Novu](https://novu.co/)** via a replaceable adapter.

This mirrors the subscription pattern: **Helm deploys Novu**, **Terraform provisions idempotent platform config** (no Helm destroy), and **`am-notification` stays vendor-agnostic** behind `INotificationProvider`.

## Repo Location

| Component | Path |
|-----------|------|
| Lean API service | `am-platform/am-notification` |
| Novu Helm deploy | `am-platform/automation/helm/deploy-novu.ps1`, `novu-values.yaml`, `novu-ingress.yaml` |
| Workflow seed | `am-platform/automation/helm/novu-workflows.json` |
| Terraform (DB + workflows, no destroy) | `am-platform/automation/terraform/notification/` |

## Tech Stack

| Layer | Stack |
|-------|-------|
| `am-notification` | Python 3.11+, FastAPI, Motor (MongoDB), aiokafka, `am-platform-security` |
| Novu (self-hosted) | Nova-Edge Helm chart — API, Worker, Web, WebSocket |
| Novu data stores | External MongoDB + external Redis (reuse infra cluster; disable bundled subcharts) |
| Automation | Terraform (`null` + local-exec scripts), PowerShell Helm scripts, npm task runner |

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Platform producers (identity, subscription, market, trade, reports)   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ Kafka domain topics (ADR-003)
                                │ am.identity.events.v1 · am.subscription.events.v1
                                │ am.usage.events.v1 · am.notification.commands.v1
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  am-notification (lean API, port 8111)                                   │
│  • Kafka consumer → canonical NotificationCommand                        │
│  • Dedupe + delivery audit (MongoDB `notification` DB)                   │
│  • Preferences overlay (category, quiet hours, critical override)        │
│  • Public inbox/preferences REST (JWT)                                   │
│  • Internal send + DLQ replay                                            │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ INotificationProvider
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  NovuProvider adapter                                                    │
│  • Upsert subscriber (Keycloak user_id)                                  │
│  • Trigger workflow by workflow_id / trigger identifier                    │
│  • Fetch/mark-read in-app feed via Novu API                              │
│  • Map Novu delivery webhooks → local audit states                       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ Novu REST API
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Novu (Helm, `notification` namespace)                                   │
│  api · worker · web (dashboard) · ws (real-time in-app)                  │
│  Workflows: email, in-app, SMS (future)                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Responsibility Split

| Concern | Owner | Notes |
|---------|-------|-------|
| Workflow design, channel routing, template rendering | **Novu** | Workflows seeded from `novu-workflows.json` |
| Email/SMS/push provider credentials | **Novu** | Configure in Novu dashboard or TF seed script |
| In-app notification feed (primary store) | **Novu** | Lean API proxies/paginates for frontend |
| Kafka consumption, event→workflow mapping | **am-notification** | Stable even if Novu is swapped |
| Dedupe, processed-events, DLQ | **am-notification** | Platform contract from `critical_high_gap_resolution.md` |
| User preferences (category, quiet hours, locale) | **am-notification** | Applied before calling provider; critical alerts bypass opt-out |
| Delivery attempt audit trail | **am-notification** | Augmented by Novu webhook callbacks |
| JWT auth for user APIs | **am-notification** | `am-platform-security` + Keycloak |

## Lean Adapter Pattern (Vendor Lock-in Prevention)

Define a narrow provider interface; only the adapter talks to Novu SDK/REST.

```python
# am_notification/providers/interface.py

class INotificationProvider(ABC):
    @abstractmethod
    async def ensure_subscriber(
        self, user_id: str, *, email: str | None = None, locale: str = "en"
    ) -> None: ...

    @abstractmethod
    async def trigger(
        self,
        *,
        workflow_key: str,
        user_id: str,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> str: ...  # provider_message_id

    @abstractmethod
    async def list_in_app(
        self, user_id: str, *, page: int, page_size: int, unread_only: bool
    ) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def mark_read(self, user_id: str, notification_ids: list[str]) -> None: ...

    @abstractmethod
    async def mark_all_read(self, user_id: str) -> None: ...
```

Implementation: `NovuProvider` in `am_notification/providers/novu_provider.py` using Novu REST (`/v1/events/trigger`, subscribers, messages). Future: `SendGridProvider`, `KnockProvider`, etc. — swap via `NOTIFICATION_PROVIDER=novu` env.

**Canonical command** (internal, not Novu-specific):

```json
{
  "event_id": "uuid",
  "correlation_id": "uuid",
  "workflow_key": "subscription.created",
  "recipient_user_id": "keycloak-sub",
  "channels": ["email", "in_app"],
  "payload": { "plan_name": "Pro", "locale": "en" },
  "critical": false
}
```

## Responsibilities & Features

- **Omni-channel delivery:** Novu workflows route to email (SMTP/provider), in-app (Novu feed + WS), SMS (future).
- **Event driven:** Kafka consumer maps platform events → `workflow_key` + payload.
- **Template management:** Owned by Novu workflows (versioned in git as `novu-workflows.json`, applied by Terraform script).
- **History & inbox:** User-facing API in `am-notification`; data sourced from Novu in-app feed (cached optionally in MongoDB for offline resilience).
- **User preferences:** Stored in MongoDB; applied before `trigger()`; security/suspension events ignore opt-out when `critical: true`.

## Supported Events & Workflow Mapping

Events arrive on **ADR-003 domain topics** (not one topic per event). The consumer reads the canonical `EventEnvelope` and routes by the `event_type` field — see [Existing Kafka event bus](#existing-kafka-event-bus) below.

| Source topic | `event_type` | `workflow_key` | Default channels | Critical |
|--------------|--------------|----------------|------------------|----------|
| `am.identity.events.v1` | `am.identity.login_new_device.v1` | `identity.login_new_device` | email, in_app | yes |
| `am.identity.events.v1` | `am.identity.password_changed.v1` | `identity.password_changed` | email, in_app | yes |
| `am.subscription.events.v1` | `am.subscription.created.v1` | `subscription.created` | email, in_app | no |
| `am.subscription.events.v1` | `am.subscription.suspended.v1` | `subscription.suspended` | email, in_app | yes |
| `am.subscription.events.v1` | `am.subscription.renewed.v1` | `subscription.renewed` | email, in_app | no |
| `am.usage.events.v1` | `am.usage.quota_exceeded.v1` | `usage.quota_exceeded` | email, in_app | no |
| TBD domain topic | `report.daily_summary` | `report.daily_summary` | email, in_app | no |
| TBD domain topic | `report.doc_parsed` | `report.doc_parsed` | in_app | no |
| TBD domain topic | `market.price_alert` | `market.price_alert` | in_app, email | no |
| TBD domain topic | `trade.executed` | `trade.executed` | in_app | no |
| `am.notification.commands.v1` | (command envelope) | per payload | per payload | per payload |

Internal synchronous path: `POST /notifications/internal/send` accepts the same canonical command shape (service token).

## API Endpoints

Public (user JWT):

```
GET    /notifications/me                — Paginated inbox (proxied from Novu via adapter)
GET    /notifications/me/unread-count   — Badge count
PATCH  /notifications/{id}/read         — Mark one read
PATCH  /notifications/read-all          — Mark all read
GET    /notifications/preferences       — User preference document
PUT    /notifications/preferences       — Update preferences
```

Internal (service account / mTLS future):

```
POST   /notifications/internal/send     — Trigger notification (bypass Kafka)
POST   /notifications/internal/replay-dlq — Replay DLQ event by id
GET    /health/live                       — Liveness
GET    /health/ready                      — Readiness (Mongo + Novu API reachable)
POST   /webhooks/novu                     — Novu delivery status → update local audit
```

Gateway prefix: `/api/notifications/*` (see Phase 8 gateway plan).

## Reliability Decision

Platform reliability rules from `critical_high_gap_resolution.md` remain in **am-notification** MongoDB even when Novu handles retries for provider channels.

### MongoDB collections (`notification` database)

| Collection | Purpose |
|------------|---------|
| `notification_preferences` | Per-user channel/category/quiet-hours/locale |
| `notification_processed_events` | Dedupe ledger |
| `notification_delivery_attempts` | Audit trail (queued → delivered / failed) |
| `notification_dlq` | Poison commands awaiting replay |

Dedupe key:

```text
event_id + workflow_key + channel + recipient_user_id
```

Delivery states (local audit):

```text
queued -> rendering -> sending -> delivered
queued -> rendering -> failed_retryable -> queued
queued -> rendering -> failed_terminal
```

Retry policy:

- **Novu** retries channel provider failures per workflow settings (1m, 5m, 15m backoff).
- **am-notification** retries Novu API `trigger` failures (3 attempts) before DLQ.
- In-app records: trigger workflow with in-app step first when multi-channel.

DLQ:

- Topic: `am.notification.commands.dlq.v1`
- Replay preserves `correlation_id` and reuses dedupe key.

## Preference Model

Stored in `notification_preferences` (not Novu subscriber custom data):

- **Channel:** `email`, `in_app`, future `sms`
- **Category:** `security`, `subscription`, `usage`, `portfolio`, `market`, `trade`, `system`
- **Quiet hours** + timezone (suppress non-critical in-app/email)
- **Language/locale** (passed to Novu payload)
- **Critical override:** `identity.*` security + `subscription.suspended` always deliver

---

## Infrastructure Reuse & Novu Integration

**No new MongoDB or Kafka deployments.** Reuse the shared infra cluster in the `infra` namespace — same pattern as `portfolio`, `market_data`, and `am_docs` services.

### Shared infra MongoDB (no new deployment)

The existing MongoDB cluster (used across the platform) gets **two scoped logical databases** with **dedicated users** — no shared credentials, no new Mongo instance.

| Database | User | Consumer | Provisioned by |
|----------|------|----------|----------------|
| `notification` | `am_notification_user` | `am-notification` (dedupe, prefs, audit) | `tf:notification:apply` |
| `novu` | `novu_user` | Novu API/worker (Helm external connection) | `tf:notification:apply` |

**Endpoints:**

| Context | Host | Port | Notes |
|---------|------|------|-------|
| In-cluster | Mongo service in `infra` namespace | `27017` | Used by Novu Helm and cluster-deployed `am-notification` |
| Local dev (TCP gateway) | `mongodb.asrax.in` | `8888` | Same gateway as portfolio/market — see `am-infra/docs/tcp_gateway_guide.md` |

**Connection string shape** (mirror `am-portfolio/.env.template`):

```text
mongodb://am_notification_user:PASSWORD@mongodb.asrax.in:8888/notification?authSource=admin&directConnection=true
mongodb://novu_user:PASSWORD@mongodb.infra.svc.cluster.local:27017/novu?authSource=admin
```

**Terraform:** `automation/terraform/notification/scripts/provision_mongo.py` — idempotent `kubectl exec` into the Mongo pod (same approach as [`provision_db.py`](../automation/terraform/billing/scripts/provision_db.py) for PostgreSQL). Creates users and grants read/write on the respective database only.

**Novu Helm:** disable bundled MongoDB subchart; set external URI to `novu_user` / `novu` on the shared cluster.

**Local dev overrides** (cluster hostnames do not resolve on laptop):

```bash
AM_NOTIFICATION_MONGO_HOST=mongodb.asrax.in
AM_NOTIFICATION_MONGO_PORT=8888
```

### Existing Kafka event bus

Reuse the existing Kafka broker in `am-infra/k8s/kafka` (`infra` namespace, `SASL_PLAINTEXT` + `SCRAM-SHA-256`).

**Bootstrap endpoints:**

| Context | Bootstrap servers |
|---------|-------------------|
| In-cluster | `kafka.infra.svc.cluster.local:9092` |
| Local dev (TCP gateway) | `kafka.asrax.in:8890` |

**Consumer topics** (`am-notification` subscribes to all; filters by `event_type` in envelope):

| Topic | Producers | Purpose |
|-------|-----------|---------|
| `am.identity.events.v1` | `am-identity` | Login, registration, password, security events |
| `am.subscription.events.v1` | `am-subscription` | Subscription lifecycle changes |
| `am.usage.events.v1` | `am-subscription`, internal services | Quota and usage threshold events |
| `am.notification.commands.v1` | Platform services | Direct async delivery commands |

**Producer topics:**

| Topic | When |
|-------|------|
| `am.notification.events.v1` | Delivery status / audit events emitted by `am-notification` |
| `am.notification.commands.dlq.v1` | Poison commands after 3 failed consumer attempts |

**Consumer group:** `am-notification-consumer`

**Event envelope** (from `adr_003_event_contracts.md` / `critical_high_gap_resolution.md`):

```json
{
  "event_id": "uuid",
  "event_type": "am.subscription.suspended.v1",
  "event_version": 1,
  "occurred_at": "2026-05-23T13:30:00Z",
  "producer": "am-subscription",
  "tenant_id": "tenant_or_org_id",
  "user_id": "keycloak_user_id_or_null",
  "correlation_id": "request_or_trace_id",
  "idempotency_key": "stable_business_key",
  "payload": {}
}
```

**Consumer behavior:**

- Parse envelope; map `event_type` → `workflow_key` (see table above).
- Store processed `event_id` in Mongo `notification_processed_events` before triggering Novu.
- Retry failed processing with exponential backoff (1m, 5m, 15m) per platform policy.
- After 3 failures, publish to `am.notification.commands.dlq.v1` (preserve `correlation_id`).
- Topics auto-create today via `KAFKA_AUTO_CREATE_TOPICS_ENABLE=true`; explicit topic provisioning can be added later.

### Redis

Reuse infra Redis (`redis.infra.svc.cluster.local`) — same pattern as Lago. Disable bundled Redis in Novu Helm values; pass external URL with password from `.secrets.env`.

### Novu Helm Deploy

Deploy with:

```bash
npm run deploy:novu
```

Files:

- `automation/helm/deploy-novu.ps1` — loads `.env` + `.secrets.env`, kubeconfig, `helm upgrade --install`
- `automation/helm/novu-values.yaml` — external Mongo/Redis, resource limits, ingress hostnames
- `automation/helm/novu-ingress.yaml` — Traefik routes (if not inline in values)

Chart source (community, production-validated before pin):

```bash
helm repo add nova-edge-charts oci://ghcr.io/nova-edge/charts
helm upgrade --install novu nova-edge-charts/novu -n notification -f novu-values.yaml
```

**Novu components:**

| Pod | Role |
|-----|------|
| `novu-api` | REST API, trigger, subscribers |
| `novu-worker` | Async workflow execution |
| `novu-web` | Admin dashboard (workflow editor) |
| `novu-ws` | WebSocket for in-app real-time |

**Ingress hostnames (env-driven, mirror Lago pattern):**

| Variable | Example |
|----------|---------|
| `NOVU_HOSTNAME` | `novu.munish.org` |
| `NOVU_API_HOSTNAME` | `novu-api.munish.org` |
| `NOVU_ASRAX_HOSTNAME` | `novu.asrax.in` |

**Resource limits (~10k users):**

| Component | Requests | Limits |
|-----------|----------|--------|
| `novu-api` | 0.5 CPU, 1Gi | 1 CPU, 2Gi |
| `novu-worker` | 1 CPU, 2Gi | 2 CPU, 4Gi |
| `novu-web` | 0.25 CPU, 512Mi | 0.5 CPU, 1Gi |
| `novu-ws` | 0.25 CPU, 512Mi | 0.5 CPU, 1Gi |

### Terraform (`automation/terraform/notification/`)

**Scope:** idempotent platform setup only — **never** manage Novu Helm release in Terraform (same as Lago → `removed.tf` with `destroy = false` if ever migrated).

```bash
npm run tf:notification:init
npm run tf:notification:plan
npm run tf:notification:apply
```

**Module responsibilities:**

1. **`null_resource.provision_mongo`** — `provision_mongo.py` via `kubectl exec` on shared infra Mongo pod:
   - User `am_notification_user` + database `notification` (read/write scoped)
   - User `novu_user` + database `novu` (read/write scoped; Novu Helm external DB)
2. **`null_resource.provision_novu_workflows`** — Idempotent sync of `novu-workflows.json` to Novu API (requires `NOVU_API_KEY` from first deploy or TF output script)
3. **Keycloak** — `am-notification-service` client already in `tf:keycloak:apply`; optional `am-novu-client` only if Novu dashboard SSO is required later

**`removed.tf` pattern:**

```hcl
# If Novu helm was ever under TF, drop management without cluster destroy:
removed {
  from = helm_release.novu
  lifecycle { destroy = false }
}
```

No `terraform destroy` workflow for notification stack — ops tear-down is manual Helm uninstall only.

### Workflow seed (`novu-workflows.json`)

Git-managed workflow definitions (trigger identifier, steps, templates). Example entry:

```json
{
  "workflow_key": "subscription.created",
  "name": "Subscription Created",
  "steps": [
    { "type": "in_app", "template": "Welcome to {{plan_name}}!" },
    { "type": "email", "subject": "Your {{plan_name}} plan is active", "template": "..." }
  ]
}
```

Applied by `automation/terraform/notification/scripts/provision_novu_workflows.py` (compare-and-upsert via Novu API).

---

## Environment Variables

Add to `.env.example` / `.secrets.env`:

```bash
# MongoDB — shared infra cluster, dedicated user (am-notification lean layer)
AM_NOTIFICATION_MONGO_URI=mongodb://am_notification_user:<password>@mongodb.asrax.in:8888/notification?authSource=admin&directConnection=true
AM_NOTIFICATION_MONGO_DATABASE=notification
# Local dev only — override host/port when cluster DNS is unreachable
AM_NOTIFICATION_MONGO_HOST=mongodb.asrax.in
AM_NOTIFICATION_MONGO_PORT=8888

# Novu external DB on same shared Mongo cluster (referenced by Helm values)
NOVU_MONGO_URI=mongodb://novu_user:<password>@mongodb.infra.svc.cluster.local:27017/novu?authSource=admin
NOVU_REDIS_URL=redis://:<REDIS_PASSWORD>@redis.infra.svc.cluster.local:6379/2

# Novu API (am-notification adapter)
NOTIFICATION_PROVIDER=novu
NOVU_API_URL=https://novu-api.munish.org
NOVU_API_KEY=<from-novu-dashboard-or-tf-seed>
NOVU_APPLICATION_IDENTIFIER=am-platform

# Service
APP_PORT=8111
AM_NOTIFICATION_CLIENT_ID=am-notification-service
AM_NOTIFICATION_CLIENT_SECRET=<from-vault>

# Kafka — existing infra broker (SCRAM-SHA-256)
KAFKA_BOOTSTRAP_SERVERS=kafka.infra.svc.cluster.local:9092
KAFKA_SECURITY_PROTOCOL=SASL_PLAINTEXT
KAFKA_SASL_MECHANISM=SCRAM-SHA-256
KAFKA_USERNAME=<infra-kafka-user>
KAFKA_PASSWORD=<from-secrets>
KAFKA_NOTIFICATION_GROUP_ID=am-notification-consumer
# Local dev only — TCP gateway (see am-infra/docs/tcp_gateway_guide.md)
AM_NOTIFICATION_KAFKA_BOOTSTRAP_SERVERS=kafka.asrax.in:8890
```

Local dev: override Mongo/Kafka/Novu hosts to VPS TCP gateway ports (same pattern as `AM_SUBSCRIPTION_POSTGRES_HOST`).

---

## npm Scripts (to add in `am-platform/package.json`)

| Script | Action |
|--------|--------|
| `deploy:novu` | Run `automation/helm/deploy-novu.ps1` |
| `tf:notification:init` | Terraform init in `automation/terraform/notification` |
| `tf:notification:plan` | Plan notification DB + workflow seed |
| `tf:notification:apply` | Apply idempotent notification provisioning |
| `notification:dev` | Run `am-notification` locally on port 8111 |

---

## Service Layout (`am-notification`)

```text
am-notification/
├── am_notification/
│   ├── main.py
│   ├── config.py
│   ├── core/                    # logging, exceptions
│   ├── providers/
│   │   ├── interface.py         # INotificationProvider
│   │   └── novu_provider.py
│   ├── services/
│   │   ├── notification_service.py
│   │   ├── preference_service.py
│   │   ├── dedupe_service.py
│   │   └── kafka_consumer.py
│   ├── models/                  # Motor collections / Pydantic schemas
│   └── routers/
│       ├── notification_router.py
│       ├── preference_router.py
│       ├── internal_router.py
│       └── webhook_router.py
├── postman/
├── pyproject.toml
└── requirements-dev.txt
```

---

## Replaceability Guide

To swap Novu for another provider:

1. Implement `INotificationProvider` for the new vendor.
2. Set `NOTIFICATION_PROVIDER=<vendor>`.
3. Migrate workflow definitions to the new system's format (keep `workflow_key` strings stable).
4. Keep Kafka mapping, dedupe, preferences, DLQ, and public REST contract unchanged in `am-notification`.
5. Update Helm/Terraform docs for the new vendor's deploy path; Novu Helm becomes optional.

Platform contracts that **must not** change when swapping providers:

- Kafka event names and canonical command JSON
- Dedupe key formula and DLQ topic
- Public REST paths under `/notifications/*`
- Preference model fields

---

## Deployment Order

1. `npm run tf:notification:apply` — scoped Mongo users (`am_notification_user`, `novu_user`) on shared infra cluster
2. `npm run deploy:novu` — Novu stack in `notification` namespace (external Mongo/Redis on shared infra)
3. Create/copy `NOVU_API_KEY` into `.secrets.env` (dashboard or seed script)
4. Re-run `npm run tf:notification:apply` — sync workflows from `novu-workflows.json`
5. Verify Kafka connectivity (in-cluster or `kafka.asrax.in:8890` locally) with SCRAM credentials
6. `npm run notification:dev` or deploy `am-notification` to cluster
7. Verify: publish test event to `am.identity.events.v1` → inbox + email in Novu dashboard

---

## Related Docs

- `critical_high_gap_resolution.md` — Gap 5 reliability decisions, Kafka topic table
- `adrs/adr_003_event_contracts.md` — Event envelope and topic naming
- `plan_subscription.md` — Reference pattern for Helm + TF split
- `am-infra/docs/tcp_gateway_guide.md` — Mongo `:8888`, Kafka `:8890` local dev access
- `task.md` — Phase 6 execution checklist
- `keycloak-realm-guide.md` — `am-notification-service` client (port 8111)
