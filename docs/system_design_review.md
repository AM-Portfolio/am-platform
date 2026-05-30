# AM Platform Main Services System Design Review

## Verdict

This review now focuses on the three main `am-platform` services only:

- `am-identity`
- `am-subscription`
- `am-notification`

Target rating after completing the requirements in this document: **10 / 10**.

Current planning quality is strong. The critical and high design gaps are now resolved as concrete decisions in `critical_high_gap_resolution.md`; the services reach production-ready 10/10 when those decisions are implemented and tested. `am-payments` remains future scope and should not block the main platform score.

## Target System Design

```text
Clients / AM Apps
      |
      v
Traefik / API Gateway (port 8000)
      |
      +--> am-identity
      |       - Internal port 8113
      |       - Keycloak adapter
      |       - Login, register, refresh, logout
      |       - User profile and settings
      |       - Service-to-service tokens
      |
      +--> am-subscription
      |       - Internal port 8110
      |       - Plans, tiers, entitlements
      |       - Subscription state machine
      |       - Usage metering and quota enforcement
      |       - PostgreSQL audit trail
      |
      +--> am-notification
      |       - Internal port 8111
      |       - Email, in-app, and SMS routing
      |       - User notification preferences
      |       - Template rendering and inbox history
      |       - MongoDB notification store

Shared Platform Layer
      |
      +--> libraries/am-platform-common
      |       - Error model, logging, event envelope, Kafka helpers
      |
      +--> libraries/am-platform-security
      |       - Keycloak JWT validation and auth dependencies
      |
      +--> automation/terraform
              - Keycloak realm, clients, service accounts, local infra

Event Backbone
      |
      +--> Kafka topics for auth, subscription, usage, and notification events
```

## Verified Strengths

- The clean-room `am-platform` boundary avoids destabilizing the existing `am-auth` services.
- Collapsing token and user-management behavior into `am-identity` reduces duplicated auth ownership.
- Keycloak as the only active provider keeps the first implementation focused.
- Subscription and notification responsibilities are separated cleanly from identity.
- Kafka is the right integration style for lifecycle events like signup, suspension, renewal, quota breach, and notification delivery.
- The fintech-specific subscription concepts are appropriate: entitlements, metered usage, audit trails, and hard suspension behavior.

## 10/10 Service Requirements

### `am-identity`

`am-identity` is the trust anchor for the platform. It should expose only clean v2-era APIs and use Keycloak as the source of truth for authentication, roles, clients, and service accounts.

Required for 10/10:

- Keycloak realm, clients, roles, groups, service accounts, and redirect URIs are managed through Terraform or repeatable seed scripts.
- Token claims are standardized: `sub`, `email`, `roles`, `tenant_id`, `org_id`, `aud`, `iss`, `scope`, `session_id`, and token type.
- Public routes are limited to register, login, refresh, logout, OTP/MFA, password reset, and OAuth callbacks.
- User routes expose `/users/me`, settings, roles, status, and profile metadata without leaking internal Keycloak details.
- Internal routes require service tokens with strict audience claims and short TTLs.
- Legacy `am-auth` cutover includes user mapping, claim compatibility, consumer migration, smoke tests, and rollback.
- Security includes rate limiting, lockout rules, MFA policy, audit logs, password reset replay protection, and refresh-token rotation.

### `am-subscription`

`am-subscription` owns the commercial access model for the AM platform. It should be the single source of truth for plans, entitlement checks, usage metering, quota enforcement, and subscription lifecycle.

Required for 10/10:

- Plans are versioned and explicit: Free, Pro, Premium, Institutional, and internal/admin tiers.
- Entitlements are modeled as machine-readable feature flags and limits, not hardcoded checks scattered across services.
- Subscription state transitions are strict and auditable: trial, active, past_due, paused, suspended, cancelled, expired.
- Usage metering is idempotent and supports daily/monthly counters, hard limits, soft limits, and audit history.
- Gateway and downstream services can call an internal entitlement API before allowing expensive or regulated actions.
- Kafka events are emitted for lifecycle and quota changes using canonical event names and schema versions.
- PostgreSQL schema includes append-only audit tables for plan changes, entitlement changes, usage events, and admin overrides.

### `am-notification`

`am-notification` owns user-facing communication and in-app inbox history. It should consume platform events and turn them into reliable, preference-aware notifications.

Required for 10/10:

- Notification preferences support channel, category, quiet hours, language, and critical-alert override rules.
- Templates are versioned, localized, reviewed, and rendered with validated variables.
- Delivery supports email and in-app first; SMS can be added after provider policy is defined.
- Delivery attempts are tracked with status, provider response, retry count, and failure reason.
- Kafka consumers are idempotent and dedupe repeated events by event ID.
- Inbox APIs support pagination, unread counts, read/read-all, and retention policy.
- Provider failures route through retry and dead-letter workflows without losing the notification record.

## Main Event Contracts

Use one canonical event namespace:

```text
am.<domain>.<event>.v1
```

Required initial events:

- `am.identity.user_registered.v1`
- `am.identity.login_succeeded.v1`
- `am.identity.login_new_device.v1`
- `am.identity.password_changed.v1`
- `am.subscription.created.v1`
- `am.subscription.changed.v1`
- `am.subscription.suspended.v1`
- `am.subscription.renewed.v1`
- `am.subscription.cancelled.v1`
- `am.usage.quota_exceeded.v1`
- `am.notification.delivery_requested.v1`
- `am.notification.delivery_failed.v1`

Every event must include `event_id`, `event_type`, `event_version`, `occurred_at`, `producer`, `tenant_id`, `user_id`, `correlation_id`, and an event-specific `payload`.

## Resolved Critical And High Gaps

Detailed decisions live in `critical_high_gap_resolution.md`.

- **Gateway and route map**: resolved by routing all public traffic through Traefik/API Gateway on port `8000`, assigning `am-identity` to internal port `8113`, and keeping `/internal/*` private.
- **Event contracts**: resolved by canonical `am.<domain>.<event>.v1` event names, standard Kafka topics, required envelope fields, retry policy, and DLQ topics.
- **Identity migration**: resolved by inventory, user mapping, shadow mode, canary, cutover, smoke tests, and rollback criteria.
- **Subscription enforcement**: resolved by gateway-level entitlement checks, downstream re-checks for high-risk actions, 60-second positive cache, idempotent metering, and fail-closed behavior.
- **Notification reliability**: resolved by persistent delivery attempts, event dedupe, retry backoff, DLQ routing, and replay tooling.

## Remaining Medium Areas Added To Tasks

- Architecture decision records for service boundaries, database ownership, event contracts, and versioning.
- CI checks for linting, typing, tests, event contracts, and build validation.
- Environment and secret-loading conventions aligned with `am-infra`.
- Observability baseline: health/readiness probes, metrics, distributed tracing, logs, and dashboard ownership.
- Backup/restore strategy for PostgreSQL, MongoDB, Keycloak realm configuration, and Kafka schemas.

## Former Key Design Risks And Resolution

1. **Port collision risk**

   Resolved. `am-identity` uses internal port `8113`; legacy `am-auth-tokens` can keep historical local port `8001`. External clients use `/api/auth/*`.

2. **Event naming drift**

   Resolved. Use `am.<domain>.<event>.v1`, for example `am.subscription.created.v1`.

3. **API gateway ownership is underdefined**

   Resolved. `critical_high_gap_resolution.md` defines public routes, internal-only route policy, auth rules, and rate limits.

4. **Identity migration is still conceptual**

   Resolved. The migration is staged as inventory, map, shadow, canary, cutover, and rollback.

5. **Notification reliability is not yet enforceable**

   Resolved. Notification delivery now requires persistent attempts, retries, DLQ, dedupe, and replay.

## Target Service Ratings

- `am-identity`: **10 / 10 target**. Reaches 10 when Keycloak automation, claims, roles, service tokens, MFA, audit logs, and legacy migration are complete.
- `am-subscription`: **10 / 10 target**. Reaches 10 when plans, entitlements, usage metering, state transitions, audit logs, and enforcement APIs are complete.
- `am-notification`: **10 / 10 target**. Reaches 10 when preferences, templates, event consumers, inbox APIs, delivery retries, dedupe, and DLQ handling are complete.

## Recommended Implementation Order

1. Establish repository skeleton, `am-platform-common`, `am-platform-security`, lint/test tooling, and local config conventions.
2. Define ADRs, OpenAPI standards, event envelope, topic names, and gateway route map.
3. Implement local infrastructure (Keycloak) and connect to existing port-forwarded PostgreSQL, Kafka, and MongoDB in the `infra` namespace.
4. Build `am-identity` with Keycloak realm/client automation and service-to-service auth.
5. Build `am-subscription` with plan catalog, entitlement checks, usage metering, and audit log.
6. Build `am-notification` with event consumers, templates, preferences, and inbox APIs.
7. Run integration tests across identity, subscription, notification, Kafka, and gateway routes.
8. Run a controlled migration from legacy auth.

## Production Readiness Checklist

- Each service exposes `/health`, `/ready`, and `/metrics`.
- Every public API has an OpenAPI contract and auth/rate-limit decision.
- Every Kafka event has a schema, version, owner, idempotency key, and retry/DLQ rule.
- Every database table or collection has an owner, backup policy, and migration plan.
- Secrets are loaded from the same conventions used by `am-infra`.
- Service-to-service calls use short-lived tokens and explicit audience claims.
- Subscription state changes are append-only and auditable.
- Notification delivery attempts are persistent and deduplicated.
- Legacy auth cutover has user mapping, client migration, smoke tests, and rollback criteria.
