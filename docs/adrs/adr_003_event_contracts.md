# ADR 003: Event Contracts & Kafka Messaging Policy

## Status
Proposed

## Context
Decoupled communication requires highly reliable event delivery, schema consistency, and failure handling. We need to standardize how events are named, formatted, verified, and replayed in case of errors.

## Decisions
1. **Event Naming Conventions:**
   All event types must follow the canonical format:
   `am.<domain>.<event_name>.v<version>` (e.g. `am.subscription.suspended.v1`).
2. **Standard Kafka Topics:**
   - Identity Events: `am.identity.events.v1`
   - Subscription Lifecycle Events: `am.subscription.events.v1`
   - Metered Usage Events: `am.usage.events.v1`
   - Notification Commands & Events: `am.notification.commands.v1` & `am.notification.events.v1`
3. **Canonical Event Envelope:**
   Every event must serialize using the generic `EventEnvelope` defined in `am-platform-common` containing:
   - `event_id` (UUID)
   - `event_type` (str)
   - `occurred_at` (ISO timestamp)
   - `correlation_id` (trace ID)
   - `idempotency_key` (stable business key)
   - `payload` (JSON DTO payload)
4. **Retry & Dead-Letter Queue (DLQ) Strategy:**
   - Failed events are retried with exponential backoff (1 min, 5 min, 15 min).
   - After 3 unsuccessful attempts, the envelope is routed to the matching DLQ topic (e.g. `am.subscription.events.dlq.v1`).
   - Consumers must enforce idempotency by storing and checking processed `event_id`s.

## Consequences
- **Pros:** Guarantees event delivery reliability, standardized format simplifies troubleshooting, prevents duplicate processing issues.
- **Cons:** Slightly complex consumer tracking code to enforce idempotency.
