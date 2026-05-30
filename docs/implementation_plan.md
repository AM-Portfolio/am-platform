# AM Platform — Full Implementation Plan
## Auth v2 (Keycloak) + Subscription + Notification

---

## Background

This plan covers the three main interconnected tracks for a 10/10 platform foundation. To maintain loose coupling, we will create a **freshly built `am-platform`** monorepo from scratch. The legacy `am-auth` repository will remain untouched and completely separated during migration. The new `am-platform` will house the unified identity layer alongside subscription and notification capabilities.

1. **am-identity** — Unified Keycloak-backed identity layer (a freshly built service in `am-platform/am-identity`, replacing the legacy `am-auth`)
2. **am-subscription** — Subscription lifecycle management (new service in `am-platform`)
3. **am-notification** — Multi-channel notification delivery (new service in `am-platform`)
4. **automation** — Monorepo-level Terraform scripts for creating and maintaining infra (e.g., Keycloak).

`am-payments` remains future scope and is not part of the main 10/10 platform score.

> [!IMPORTANT]
> **Non-negotiable constraints:**
> - **Drop v1 routes completely**. The new unified service acts as a clean adapter over Keycloak.
> - **Consolidate** `am-auth-tokens` and `am-user-management` into a single `am-identity` microservice.
> - No Docker deployment unless explicitly requested
> - Terraform state backend: **local**
> - Keycloak only (Authentik is wired as a stub for later)
> - New Java services follow the **Maven multi-module pattern** (Spring Boot 3.2, Java 17, Lombok, Kafka, OpenTelemetry)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Traefik (port 8000)                          │
└───┬───────────────────────────────┬─────────────────────────────────┘
    │                               │
    ▼                               ▼
am-platform/ (UNIFIED MONOREPO)
├── am-identity              (port 8113)
├── am-subscription          (port 8110)
├── am-notification          (port 8111)
└── automation               (Terraform)
    │                               │
    │  ◄────────────────────────────┤  Keycloak Token Validation
    │                               │
    └─ Keycloak ◄───────────────────┤
       (port 8180)                  │
                                    │
                                  Kafka (events)
```

---

## User Review Required

I have redesigned the architecture. We will use a freshly created monorepo called `am-platform`. The legacy `am-auth` repo will NOT be moved here; it will stay isolated. `am-platform` will house freshly built `am-identity`, `am-subscription`, and `am-notification` services. This prevents breaking existing features while letting us build the new platform cleanly from scratch.

Please review this new topology.

---

## Port Allocation (extending global rules)

| Port | Service | Repo |
|------|---------|------|
| 8113 | am-identity (Unified tokens + users) | am-platform/am-identity |
| 8110 | am-subscription | am-platform |
| 8111 | am-notification | am-platform |
| 8180 | Keycloak | External / local |

`8001` remains reserved for the legacy `am-auth-tokens` local service during migration. External clients should use Traefik/API Gateway routes such as `/api/auth/*`, not direct service ports.

---

## Track 1: am-identity (Unified Keycloak Adapter)

See detailed plan: [plan_identity.md](file:///a:/InfraCode/AM-Portfolio-grp/am-platform/plan_identity.md)

---

### 1.3 Terraform moved to Monorepo Root

(See Section 2.1 - The Terraform automation is moved to the root of the `am-platform` monorepo to maintain all infrastructure, including Keycloak).

---

## Track 2: am-platform (UNIFIED MONOREPO)

We will create a fresh monorepo `am-platform` in the `a:/InfraCode/AM-Portfolio-grp/` directory from scratch.

### 2.1 Monorepo Structure

```
am-platform/
├── automation/                      — Unified Terraform scripts for infrastructure (Keycloak, DBs, Kafka)
│   └── terraform/
│       ├── main.tf                  — Root module
│       └── modules/                 — keycloak-realm, keycloak-clients, etc.
├── am-identity/                     — Freshly built Unified Python Auth service
├── pyproject.toml                   — Root Poetry config (if using workspaces) or separate per service
├── libraries/
│   ├── am-platform-common           — Shared Pydantic DTOs and utilities
│   └── am-platform-security         — Keycloak JWT FastAPI dependency
└── services/
    ├── am-subscription/             — Port 8110
    └── am-notification/             — Port 8111
```

### 2.2 am-subscription

See detailed plan: [plan_subscription.md](file:///a:/InfraCode/AM-Portfolio-grp/am-platform/plan_subscription.md)

### 2.3 am-notification

See detailed plan: [plan_notification.md](file:///a:/InfraCode/AM-Portfolio-grp/am-platform/plan_notification.md)

### 2.4 Critical and High Gap Resolution

See resolved decisions: [critical_high_gap_resolution.md](file:///a:/InfraCode/AM-Portfolio-grp/am-platform/critical_high_gap_resolution.md)

---

## Event Flow Diagram

```
User subscribes (am-subscription)
         │
         ▼ Kafka: am.subscription.created.v1
         │
         ├──► am-notification: sends welcome email
```

---

## Implementation Order (Execution Sequence)

| Phase | Track | Work | Est. |
|-------|-------|------|------|
| 1 | am-identity | Scaffold new unified Python API | Now |
| 2 | am-identity | Migrate IIdentityProvider logic to new routes | Now |
| 3 | am-platform | Scaffold new `am-platform` monorepo structure | Next |
| 4 | automation | Create Terraform module for Keycloak | Next |
| 5 | am-subscription | Service scaffold (FastAPI) | Next |
| 6 | am-notification | Service scaffold (FastAPI) | Next |
| 7 | All | Integration tests for gateway, auth, events, entitlement checks, and notification delivery | Next |
| 8 | All | Architecture diagram and production readiness review | Last |
