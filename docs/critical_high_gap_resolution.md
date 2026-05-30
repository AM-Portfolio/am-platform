# Critical And High Gap Resolution

This document resolves the critical and high gaps for the 10/10 `am-platform` main services: `am-identity`, `am-subscription`, and `am-notification`.

## Resolved Gap 1: Gateway And Route Map

Decision: all external traffic enters through Traefik/API Gateway on port `8000`. Services do not expose internal routes publicly.

| Public Route | Service | Internal Port | Auth Rule | Rate Limit |
|---|---|---:|---|---|
| `/api/auth/register` | `am-identity` | `8113` | Public | 10/min/IP |
| `/api/auth/login` | `am-identity` | `8113` | Public | 10/min/IP + account lockout |
| `/api/auth/refresh` | `am-identity` | `8113` | Refresh token | 30/min/user |
| `/api/auth/logout` | `am-identity` | `8113` | Access token | 30/min/user |
| `/api/auth/password-reset` | `am-identity` | `8113` | Public | 5/min/IP |
| `/api/auth/otp/*` | `am-identity` | `8113` | Public challenge flow | 10/min/IP |
| `/api/users/me` | `am-identity` | `8113` | Access token | 120/min/user |
| `/api/users/me/settings` | `am-identity` | `8113` | Access token | 60/min/user |
| `/api/subscriptions/plans` | `am-subscription` | `8110` | Optional access token | 120/min/IP |
| `/api/subscriptions/me` | `am-subscription` | `8110` | Access token | 120/min/user |
| `/api/subscriptions/*` | `am-subscription` | `8110` | Access token | 60/min/user |
| `/api/notifications/me` | `am-notification` | `8111` | Access token | 120/min/user |
| `/api/notifications/preferences` | `am-notification` | `8111` | Access token | 60/min/user |

Internal-only routes:

- `/internal/*` is never externally routed.
- Internal calls require service tokens with `aud` equal to the target service.
- Gateway denies requests with user tokens to internal routes.

Port collision resolution:

- Legacy `am-auth-tokens` keeps historical local port `8001`.
- New `am-identity` uses internal port `8113`.
- Public auth traffic uses `/api/auth/*` through Traefik/API Gateway, not direct service ports.

## Resolved Gap 2: Event Contracts

Decision: all main-service events use a single canonical namespace and an explicit envelope.

Event naming format:

```text
am.<domain>.<event>.v1
```

Kafka topics:

| Topic | Producers | Consumers | Purpose |
|---|---|---|---|
| `am.identity.events.v1` | `am-identity` | `am-notification`, audit consumers | Login, registration, password, and security events |
| `am.subscription.events.v1` | `am-subscription` | `am-notification`, gateway cache updater | Subscription lifecycle changes |
| `am.usage.events.v1` | `am-subscription`, internal services | `am-notification`, analytics | Quota and usage threshold events |
| `am.notification.commands.v1` | Platform services | `am-notification` | Direct async delivery requests |
| `am.notification.events.v1` | `am-notification` | audit consumers | Delivery status events |

Dead-letter topics:

- `am.identity.events.dlq.v1`
- `am.subscription.events.dlq.v1`
- `am.usage.events.dlq.v1`
- `am.notification.commands.dlq.v1`
- `am.notification.events.dlq.v1`

Required event envelope:

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

Retry policy:

- Consumer retries use exponential backoff: 1 minute, 5 minutes, 15 minutes.
- After 3 failed attempts, publish to the matching DLQ.
- Consumers must store processed `event_id` values or equivalent idempotency records.

## Resolved Gap 3: Identity Migration

Decision: the migration from legacy `am-auth` to `am-identity` is a controlled cutover, not a silent replacement.

Migration stages:

1. **Inventory**: list current clients, routes, token claims, roles, user IDs, and frontend dependencies.
2. **Map**: map legacy users to Keycloak `sub`; keep stable external user IDs where existing data depends on them.
3. **Shadow**: run `am-identity` on port `8113` behind non-default gateway routes and compare login/profile responses.
4. **Canary**: route selected clients to `/api/auth/*` backed by `am-identity`.
5. **Cutover**: move all new auth traffic to `am-identity`; freeze legacy user writes.
6. **Rollback**: restore gateway route to legacy auth and disable Keycloak writes if smoke tests fail.

Required smoke tests:

- Register, login, refresh, logout.
- Password reset request and confirmation.
- `/users/me` profile and settings retrieval.
- Service token generation and validation.
- Role and entitlement claim propagation to `am-subscription`.

Rollback criteria:

- Login success rate drops below agreed baseline.
- Token validation fails for active clients.
- User profile lookup mismatch is detected.
- Gateway cannot validate service-to-service audience claims.

## Resolved Gap 4: Subscription Enforcement

Decision: entitlement checks are enforced both at the gateway and inside downstream services.

Enforcement flow:

1. User calls a protected AM route.
2. Gateway validates access token through `am-platform-security`.
3. Gateway checks `am-subscription` internal entitlement API for route-level requirements.
4. Gateway caches positive entitlement decisions for up to 60 seconds.
5. Downstream high-risk services re-check entitlements before regulated, expensive, or state-changing actions.
6. `am-subscription` records usage through an idempotent meter endpoint.

Internal entitlement API:

```text
GET  /subscriptions/internal/entitlements/{user_id}
POST /subscriptions/internal/check
POST /subscriptions/internal/meter
```

Required `POST /subscriptions/internal/check` request:

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

## Resolved Gap 5: Notification Reliability

Decision: notifications use a persistent delivery record, dedupe by event and channel, retry provider failures, and support DLQ replay.

Collections:

- `notification_templates`
- `notification_preferences`
- `notification_inbox`
- `notification_delivery_attempts`
- `notification_processed_events`

Dedupe key:

```text
event_id + template_key + channel + recipient_user_id
```

Delivery states:

```text
queued -> rendering -> sending -> delivered
queued -> rendering -> failed_retryable -> queued
queued -> rendering -> failed_terminal
```

Retry policy:

- Retry email/SMS provider failures after 1 minute, 5 minutes, and 15 minutes.
- Stop retrying after 3 provider failures unless manually replayed.
- In-app notification records are created before external channel attempts.

DLQ handling:

- Poison events go to `am.notification.commands.dlq.v1`.
- Replay tooling must accept a DLQ event ID and preserve the original `correlation_id`.
- Replayed events must still use the same dedupe key to prevent duplicate inbox rows.

## Status

These gaps are considered design-resolved. Implementation tasks remain in `task.md` and must be completed before the services can be rated as production-ready 10/10.
