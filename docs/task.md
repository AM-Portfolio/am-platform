# AM Platform - Execution Tasks

## Phase 1: Foundation & Shared Vocabulary
- `[x]` Initialize Python Monorepo structure in `am-platform/`
- `[x]` Setup `libraries/am-platform-common`
- `[x]` Define standard JSON structured logging inside `am-platform-common`
- `[x]` Define standard error models and Pydantic base models in `am-platform-common`
- `[x]` Resolve critical/high design gaps in `critical_high_gap_resolution.md`
- `[x]` Define ADRs for service boundaries, database ownership, and event contracts
- `[x]` Define OpenAPI standards, versioning policy, and shared request/response envelope

## Phase 2: Infrastructure & Automation
- `[x]` Setup `automation/terraform` folder
- `[x]` Setup `automation/helm` configuration and PowerShell deploy scripts for Keycloak and Lago on VPS
- `[x]` Setup `am-platform/package.json` task runner configurations
- `[x]` Deploy Keycloak via Helm on VPS in `identity` namespace and verify connection to Postgres db
- `[x]` Add CI pipeline for lint, type checks, unit tests, contract tests, and container build validation
- `[x]` Add local `.env.example` and secret-loading conventions compatible with `am-infra`

## Phase 3: Core Security & Auth (am-identity)
- `[x]` Setup `libraries/am-platform-security` with FastAPI dependencies for JWT token validation
- `[x]` Scaffold `am-platform/am-identity` FastAPI service
- `[x]` Implement `IIdentityProvider` Keycloak adapter
- `[x]` Implement `POST /auth/login`, `/auth/register`, `/auth/refresh`, and OTP routes
- `[x]` Implement `GET /users/me` and `/users/me/settings` for frontend user page
- `[x]` Implement Server-to-Server Auth tokens (`/internal/auth/service-token`)
- `[x]` Verify `am-identity` against local Keycloak
- `[x]` Define 10/10 identity claim model, role mapping, token TTLs, refresh-token rotation, MFA policy, and audit log requirements
- `[x]` Automate Keycloak realm, clients, roles, groups, service accounts, and redirect URIs
- `[x]` Add legacy `am-auth` cutover plan with smoke tests and rollback criteria
- `[ ]` Implement legacy `am-auth` cutover smoke tests and rollback automation

## Phase 4: Event Bus (Kafka)
- `[ ]` Add standard Kafka Producer/Consumer classes in `am-platform-common`
- `[x]` Define canonical Kafka topic names, event schema versions, idempotency keys, and retry/DLQ policy
- `[ ]` Add event contract tests for identity, subscription, usage, and notification events

## Phase 5: Business Logic - Subscription & Lean Company Wrapper
- `[ ]` **Infrastructure & Config**
  - `[x]` Provision logical DB `subscription` on existing `infra` PostgreSQL via Terraform (`tf:billing:apply`)
  - `[x]` Provision Lago Helm chart (`billing` namespace, UI enabled, external DB/Redis) via `deploy:lago`
  - `[x]` Provision Keycloak confidential clients (`am-lago-client` + core service clients) via `tf:keycloak:apply`
- `[ ]` **FastAPI Service Scaffold (`am-subscription`)**
  - `[x]` Integrate `am-platform-security` (JWT auth) for all internal/external routes
  - `[x]` Implement DB Schema (PostgreSQL) for internal models: `Subscription`, `MeterBuffer`, `ProviderMap`
- `[ ]` **Lean Company Wrapper Implementation**
  - `[x]` Define lean Interfaces (`ISubscriptionProvider`, `IMeteringProvider`) for vendor lock-in prevention
  - `[x]` Implement `LagoProvider` adapter to handle Lago API calls using `am-lago-client` token
  - `[x]` Implement generic `/webhooks/provider` endpoint to translate vendor webhooks to canonical Kafka events
- `[ ]` **Entitlements & Metering**
  - `[x]` Implement internal entitlement API for Gateway enforcement (caching positive checks)
  - `[x]` Implement async idempotent usage metering (record locally -> async sync to provider)
  - `[ ]` Emit `am.subscription.created.v1`, `am.usage.quota_exceeded.v1`, and `am.subscription.suspended.v1` events to Kafka
  - `[x]` Define 10/10 subscription state machine: trial, active, past_due, paused, suspended, cancelled, expired
  - `[x]` Define internal entitlement API for gateway and downstream service enforcement

## Phase 6: Business Logic - Notification & Novu Adapter
- `[x]` **Infrastructure & Config**
  - `[x]` Provision scoped Mongo users on **shared infra Mongo cluster** via Terraform (`am_notification_user`/`notification`, `novu_user`/`novu`) — `tf:notification:apply`, idempotent, no destroy
  - `[x]` Deploy Novu Helm chart (`notification` namespace, external Mongo/Redis on shared infra) via `deploy:novu`
  - `[x]` Add `novu-workflows.json` + idempotent workflow seed script in Terraform (`provision_novu_workflows.py`)
  - `[x]` Add env vars to `.env.example` / `.secrets.env`: Mongo URIs (TCP gateway `:8888` local), Kafka SCRAM creds, Novu API (`NOVU_API_URL`, `NOVU_API_KEY`)
  - `[x]` Keycloak confidential client `am-notification-service` via `tf:keycloak:apply`
- `[x]` **FastAPI Service Scaffold (`am-notification`, port 8111)**
  - `[x]` Scaffold `am-platform/am-notification` (FastAPI, Motor, structured logging, health/readiness)
  - `[x]` Integrate `am-platform-security` (JWT) for public routes; service token for internal routes
  - `[x]` Implement MongoDB collections: `notification_preferences`, `notification_processed_events`, `notification_delivery_attempts`, `notification_dlq`
- `[x]` **Lean Provider Wrapper (Novu adapter)**
  - `[x]` Define `INotificationProvider` interface for vendor lock-in prevention
  - `[x]` Implement `NovuProvider` adapter (subscriber upsert, trigger workflow, in-app feed read/mark-read)
  - `[x]` Implement `POST /webhooks/novu` to map Novu delivery callbacks → local audit states
  - `[x]` Wire `NOTIFICATION_PROVIDER=novu` config switch for future provider swap
- `[ ]` **Kafka & Delivery**
  - `[x]` Connect Kafka consumer to existing infra broker (SCRAM-SHA-256; local dev via `kafka.asrax.in:8890`)
  - `[x]` Subscribe to ADR-003 domain topics: `am.identity.events.v1`, `am.subscription.events.v1`, `am.usage.events.v1`, `am.notification.commands.v1`
  - `[x]` Filter by `event_type` in EventEnvelope → canonical `NotificationCommand` → Novu `workflow_key` (see `plan_notification.md`)
  - `[ ]` Emit delivery status to `am.notification.events.v1`
  - `[x]` Apply user preferences (channel, category, quiet hours) before trigger; honor critical-alert override
  - `[x]` Implement event dedupe by `event_id + workflow_key + channel + recipient_user_id`
  - `[ ]` Implement Novu API retry (3 attempts) + DLQ topic `am.notification.commands.dlq.v1` + replay tooling
- `[x]` **Inbox & Preferences APIs**
  - `[x]` Implement `GET /notifications/me`, unread count, mark read, mark all read (via NovuProvider)
  - `[x]` Implement `GET/PUT /notifications/preferences`
  - `[x]` Implement `POST /notifications/internal/send` for synchronous alerts
  - `[x]` Add Postman collection mirroring `am-identity` / `am-subscription` pattern
- `[x]` Add notification template versioning, delivery retry policy, and provider failure handling design
- `[x]` Define 10/10 notification preferences: channel, category, quiet hours, language, and critical-alert override rules

## Phase 7: Payments (Future Integration)
- `[ ]` Scaffold `am-platform/am-payments` (To be tackled later as per plan)
- `[ ]` Define payment webhook verification, replay protection, and financial ledger invariants before implementation

## Phase 8: Production Readiness & Migration
- `[x]` Add API gateway route plan for `/api/auth`, `/api/subscriptions`, and `/api/notifications`
- `[ ]` Add observability baseline: health/readiness endpoints, metrics, tracing, and dashboard ownership
- `[ ]` Add backup/restore strategy for PostgreSQL, MongoDB, Keycloak realm config, and Kafka schemas
- `[x]` Add migration/cutover plan from legacy `am-auth` to `am-identity`, including rollback criteria
- `[x]` Add Terraform for subscription DB user; Lago via Helm; Keycloak clients via Terraform
- `[x]` Add Terraform for notification Mongo scoped users on shared cluster + Novu workflow seed; Novu via Helm; existing Kafka SCRAM creds in `.secrets.env`
- `[ ]` Generate `.secrets.env` entries for new clients and Lago credentials
- `[ ]` Update docs (keycloak-realm-guide, plan_subscription, architecture diagram)
