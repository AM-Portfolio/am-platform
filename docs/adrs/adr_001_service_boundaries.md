# ADR 001: Service Boundaries & Communication Patterns

## Status
Proposed

## Context
The platform requires a robust architecture for three core services:
1. `am-identity` (Authentication, user profile/settings)
2. `am-subscription` (Subscription lifecycle, entitlements checking)
3. `am-notification` (User alert delivery, inbox history)

We need to define clear boundaries between these domains and determine how services interact with each other.

## Decisions
1. **Service Separation:**
   Each service will run as a separate, self-contained microservice with its own business logic, API interface, and data store.
2. **Synchronous Communication (REST/HTTP):**
   - External clients always query services via REST APIs exposed through the Traefik Gateway (port 8000).
   - High-priority, real-time validations (such as checking if an active user has the entitlement to perform an action) will use internal HTTP endpoints.
3. **Asynchronous Communication (Kafka):**
   - High-latency, decoupled, or event-based workflows (e.g., sending a welcome email, locking accounts, recording analytics logs) will utilize asynchronous event-driven messages published to Kafka.
4. **Gateway Dependency:**
   No service will directly handle public internet traffic; all requests pass through the central Gateway.

## Consequences
- **Pros:** High decoupling, services can scale independently, failures are isolated to individual services.
- **Cons:** Slightly increased latency for synchronous checks (mitigated by 60s gateway caching), requiring robust event validation schemas.
