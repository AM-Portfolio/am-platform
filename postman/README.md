# AM Platform — Postman

Unified API tests for all thin-layer services in one collection.

## Import

1. Postman → **Import**
2. Select:
   - `AM-Platform.postman_collection.json`
   - `AM-Platform.local.postman_environment.json` (local dev)
   - `AM-Platform.preprod.postman_environment.json` (preprod gateway)
3. Activate the environment that matches where services run
4. Paste secrets from `.secrets.env` (see table below)

## Environments

| File | When to use | Service base URLs |
|------|-------------|-------------------|
| **AM Platform — Local** | `npm run platform:dev` | `localhost:8113` / `8110` / `8111` |
| **AM Platform — Preprod** | Deployed behind gateway | `https://am-dev.asrax.in/api` (all modules) |

Preprod assumes Traefik routes `/api/auth/*`, `/api/subscriptions/*`, `/api/notifications/*` to platform pods. Adjust `environment.defaults.json` if your gateway paths differ.

## Auto-capture scripts

The collection includes **Pre-request** and **Tests** (post-response) scripts (`postman/scripts/`).

### Pre-request (`collection-prerequest.js`)

- Sets fresh `idempotency_key` for internal meter/check POSTs
- Adds `X-Request-Id` header
- Tracks `last_request_name`, `last_request_url`

### Post-response (`collection-test.js`)

On 2xx responses, auto-saves to the **active environment**:

| Response field | Environment key |
|----------------|-----------------|
| `access_token` (user login) | `access_token`, `user_sub` (from JWT) |
| `access_token` (client_credentials) | `service_access_token` |
| `refresh_token` | `refresh_token` |
| `sub` / `user_id` | `user_sub` |
| `data.id` (subscription) | `subscription_id` |
| `data.plan_code` / plans list | `plan_code` |
| `state`, `auth_url` | `google_state`, `google_auth_url` |
| notification id | `notification_id` |

Also sets `last_response_status` for debugging.

## Secrets (both environments)

| Environment variable | `.secrets.env` key |
|---------------------|-------------------|
| `identity_client_secret` | `AM_IDENTITY_CLIENT_SECRET` |
| `portfolio_client_secret` | `AM_PORTFOLIO_CLIENT_SECRET` |
| `gateway_client_secret` | `AM_GATEWAY_CLIENT_SECRET` |
| `notification_client_secret` | `AM_NOTIFICATION_CLIENT_SECRET` |

## Folder layout

```
AM Platform/
├── Identity/
├── Subscription/
└── Notification/
```

## Typical local flow

```text
npm run platform:dev
→ Identity → 00 Health → Health Check
→ Identity → 02 Auth → Login (Password)     # sets access_token, user_sub
→ Subscription → 02 Subscriptions → Get My Subscription   # sets subscription_id
→ Notification → 99 Keycloak → Client Credentials         # sets service_access_token
→ Notification → 03 Internal → Send Notification
```

## Regenerate

After editing module collections or scripts:

```bash
python postman/build_platform_postman.py
```

Edits to `environment.defaults.json` or `postman/scripts/*.js` are picked up on rebuild.

## Per-service collections (unchanged)

- `am-identity/postman/`
- `am-subscription/postman/`
- `am-notification/postman/`
