# AM Platform — Postman

Unified API tests for all thin-layer services in one collection.

## Prefer these environments (Asrax workspace)

Use the shared ecosystem envs (created from `am_environment.defaults.json`):

| Environment | Host |
|-------------|------|
| **AM — Local** | localhost per-service ports |
| **AM — Dev** | `https://am-dev.asrax.in` |
| **AM — Preprod** | `https://am-preprod.asrax.in` |
| **AM — Prod** | `https://am.asrax.in` |

Generate locally:

```bash
python postman/build_am_envs.py
```

Sync envs / normalize collections (Postman API key in `~/.am/credentials.env`):

```bash
python postman/sync_am_postman.py --envs-only
python postman/normalize_collections.py
```

Legacy `AM Platform — *` and other older environments are kept; prefer **AM — *** day to day.

## Import (platform collection)

1. Postman → **Import**
2. Select:
   - `AM-Platform.postman_collection.json`
   - `AM.local|dev|preprod|prod.postman_environment.json` (or use cloud **AM — ***)
3. Activate the matching environment
4. Paste secrets from `.secrets.env` (see table below)

## Environments (platform module files)

| File | When to use | Service base URLs |
|------|-------------|-------------------|
| **AM — Local** / Platform Local | `npm run platform:dev` | `localhost:8113` / `8110` / `8111` |
| **AM — Dev/Preprod/Prod** | Gateway | `/identity`, `/subscriptions`, `/notifications` on the stage host |

Adjust `am_environment.defaults.json` (shared) or `environment.defaults.json` (platform-only rebuild) if gateway paths differ.

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

Shared AM envs:

```bash
python postman/build_am_envs.py
```

Platform collection (Identity/Subscription/Notification merge):

```bash
python postman/build_platform_postman.py
```

Edits to `am_environment.defaults.json` / `environment.defaults.json` or `postman/scripts/*.js` are picked up on rebuild.

## Per-service collections (unchanged)

- `am-identity/postman/`
- `am-subscription/postman/`
- `am-notification/postman/`
