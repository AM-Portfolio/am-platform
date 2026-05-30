# AM Platform

`am-platform` is the planned clean-room platform monorepo for the three main shared capabilities across the AM ecosystem: identity, subscription, and notification.

## Documents

- `implementation_plan.md` - primary implementation plan and service topology.
- `system_design_review.md` - verified system design, gap review, and ratings.
- `critical_high_gap_resolution.md` - resolved decisions for gateway routing, events, migration, subscription enforcement, and notification reliability.
- `task.md` - execution checklist.
- `plan_identity.md` - Keycloak-backed identity service plan.
- `plan_subscription.md` - subscription, entitlements, and usage plan.
- `plan_notification.md` - notification routing and inbox plan.
- `plan_payments.md` - future payment abstraction and billing plan, outside the main 10/10 platform score.

## Current Status

This folder currently contains planning artifacts only. The planned executable structure is:

```text
am-platform/
├── automation/terraform/
├── am-identity/
├── libraries/
│   ├── am-platform-common/
│   └── am-platform-security/
└── services/
    ├── am-subscription/
    └── am-notification/
```

## Recommended Next Step

Start with the 10/10 foundation for `am-identity`, `am-subscription`, and `am-notification`: shared libraries, OpenAPI contracts, Kafka event schemas, gateway route mapping, and local Keycloak infrastructure integrated with existing `infra` namespace services.
