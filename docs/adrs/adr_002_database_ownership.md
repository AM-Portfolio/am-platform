# ADR 002: Database Ownership & Schema Isolation

## Status
Proposed

## Context
Shared database access is a known microservice anti-pattern that leads to tight coupling, deployment blocks, and data corruption risks. We need to define schema ownership rules for PostgreSQL, MongoDB, and Keycloak storage.

## Decisions
1. **Strict Service Isolation:**
   No service is allowed to read from or write to another service's database. Database schemas are owned by exactly one service.
2. **Database Types & Responsibility:**
   - **`am-identity`**: Keycloak manages user authentication schemas directly. Local settings or application-specific profile metadata are persisted through Keycloak user attributes or handled purely via OAuth token context.
   - **`am-subscription`**: PostgreSQL manages plans, active user subscriptions, entitlements, and immutable audit trails. Relational constraints enforce state integrity.
   - **`am-notification`**: MongoDB manages template versions, inbox history, preferences, and delivery logs. This document store supports highly dynamic template structures and unstructured provider logs.
3. **Database Sharing Prohibited:**
   Cross-service queries must be executed via public APIs or synchronous internal REST check endpoints.

## Consequences
- **Pros:** Total deployment independence, no database-level lock contentions, optimized database technology selection per domain.
- **Cons:** Shared queries require network calls, eventual consistency must be handled for read models.
