# AM Subscription Service

FastAPI service for subscription lifecycle, entitlements, and usage metering. Port **8110**.

## Run locally

```bash
cd am-platform
npm run subscription:dev
```

Requires PostgreSQL `subscription` database (provision via `npm run tf:billing:apply`) and Lago API key in `.secrets.env`.

Python deps (once per venv):

```bash
pip install -r am-platform/requirements-dev.txt
```

## API routes

| Method | Path | Auth |
|--------|------|------|
| GET | `/subscriptions/plans` | Public |
| POST | `/subscriptions` | User JWT |
| GET | `/subscriptions/me` | User JWT |
| PATCH | `/subscriptions/{id}/cancel` | User JWT |
| PATCH | `/subscriptions/{id}/pause` | User JWT |
| PATCH | `/subscriptions/{id}/resume` | User JWT |
| PATCH | `/subscriptions/{id}/upgrade` | User JWT |
| GET | `/subscriptions/usage/history` | User JWT |
| GET | `/subscriptions/internal/entitlements/{user_id}` | Service token |
| POST | `/subscriptions/internal/check` | Service token |
| POST | `/subscriptions/internal/meter` | Service token |
| POST | `/webhooks/provider` | Provider webhook |

Plans and limits are loaded from `automation/helm/lago-plans.json`. Billing sync uses Lago (`LAGO_ORG_API_KEY`).

## Postman

Import `postman/AM-Subscription.postman_collection.json` and `postman/AM-Subscription.local.postman_environment.json`. See `postman/README.md`.
