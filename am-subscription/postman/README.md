# AM Subscription — Postman

## Import

1. Open Postman → **Import**
2. Select both files:
   - `AM-Subscription.postman_collection.json`
   - `AM-Subscription.local.postman_environment.json`
3. Activate environment **AM Subscription — Local**
4. Set secrets in the environment:
   - `portfolio_client_secret` ← `.secrets.env` → `AM_PORTFOLIO_CLIENT_SECRET`
   - `gateway_client_secret` ← `.secrets.env` → `AM_GATEWAY_CLIENT_SECRET`
   - `test_email` / `test_password` for user JWT flows

## Run locally

```bash
cd am-platform
npm run subscription:dev
```

Also run **am-identity** (port 8113) if you use the identity login helper folder.

## Recommended test order

| Step | Request |
|------|---------|
| 1 | `00 Health` → Health Check |
| 2 | `01 Plans` → List All Plans |
| 3 | `99 Keycloak Helpers` → Password Login (am-web-client) **or** use AM Identity collection login |
| 4 | `02 Subscriptions` → Get My Subscription |
| 5 | `02 Subscriptions` → Upgrade to Pro |
| 6 | `02 Subscriptions` → Usage History |
| 7 | `99 Keycloak Helpers` → Client Credentials (am-portfolio-service) |
| 8 | `03 Internal` → Check Entitlement / Record Meter |

### User JWT (401 troubleshooting)

- **Issuer mismatch:** Keycloak tokens use `http://auth.munish.org/...` — fixed in `am-platform-security` (http/https tolerated).
- **Expired token:** am-identity access tokens are short-lived (~5 min). Re-run **99 Keycloak Helpers → Password Login** or **AM Identity → Login (Password)** before subscription calls.
- Use the **user** `access_token` from login, not the service-account token from Client Credentials.


1. `99 Keycloak Helpers` → Client Credentials (am-portfolio-service)
2. Set `user_sub` from a logged-in user's JWT `sub` claim
3. Run `03 Internal` requests with `service_access_token`

### Webhooks

`04 Webhooks` → Provider Webhook simulates a Lago billing event (no auth).

## Auto-saved variables

Collection test scripts set:

- `access_token` — user JWT from Keycloak helpers
- `service_access_token` — machine token for internal routes
- `subscription_id` — from `data.id` on subscription responses
- `user_sub` — from subscription `data.user_id`
- `idempotency_key` — generated UUID for meter/check calls

## Gateway (future)

Public routes via Traefik: `/api/subscriptions/*`
