# AM Platform — Postman

Unified API tests for all thin-layer services in **one** collection. Import **AM Platform** only.

Do **not** import `am-identity/postman/AM-Identity.postman_collection.json` into Postman. That file is the Identity **source** for the builder. Importing both creates duplicate folders.

## Import

1. Postman → **Import**
2. Select:
   - `AM-Platform.postman_collection.json`
   - `AM-Platform.local.postman_environment.json` (local dev)
   - `AM-Platform.preprod.postman_environment.json` / `AM-Platform.prod.postman_environment.json` as needed
3. Activate the environment that matches where services run
4. Paste secrets from `.secrets.env` (see table below)

If an old **AM Identity Service** collection is still in the workspace, archive or delete it after a fresh import/sync.

## Environments

| File | When to use | Service base URLs |
|------|-------------|-------------------|
| **AM Platform — Local** | `npm run platform:dev` | `localhost:8113` / `8110` / `8111` |
| **AM Platform — Dev** | am-dev gateway | `https://am-dev.asrax.in/identity` (and sibling paths) |
| **AM Platform — Preprod / Prod** | Live cluster | `https://am.asrax.in/identity` (and sibling paths) |

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
| `tokens.access_token` (web OTP verify) | `access_token` |
| `access_token` (client_credentials) | `service_access_token` |
| `refresh_token` | `refresh_token` |
| `sub` / `user_id` | `user_sub` |
| `data.id` (subscription) | `subscription_id` |
| `data.plan_code` / plans list | `plan_code` |
| `state`, `auth_url` | `google_state`, `google_auth_url` |
| notification id | `notification_id` |
| `device_link_id` / `confirmation_code` | QR vars |
| `otp_session_id` | web OTP |

Also sets `last_response_status` for debugging. Platform Logins also set `login_platform` and `oauth_client_id`.

## Secrets (all environments)

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
│   ├── Auth/
│   │   ├── Login & Session         # Login / Refresh / Logout (Web, Android, iOS)
│   │   ├── Web OTP                 # working OTP
│   │   └── Deprecated              # /auth/login/otp 501 stub
│   ├── Flows (run in order)/
│   │   ├── QR login (no phone)     # Start → Android login → Approve → Poll
│   │   └── Web OTP (email)
│   └── Device Link                 # individual QR APIs
├── Subscription/
└── Notification/
```

## Typical local flow

```text
npm run platform:dev
→ Identity → 00 Health → Health Check
→ Identity → Auth → Login & Session → Login (Web) or Login (Android)
→ Identity → 04 Users → Get My Profile
```

### QR without a phone

```text
Identity → Flows (run in order) → QR login (no phone)
1 Device Link Start
2 Login (Android — fake phone Bearer)
3 Device Link Approve
4 Device Link Poll Approved
```

TTL is ~120s; run Approve immediately after Start.

### Web OTP (not `/auth/login/otp`)

```text
Identity → Flows (run in order) → Web OTP (email)
1 Send → copy code from email into web_otp_code
2 Verify
```

## Regenerate

After editing `am-identity/postman/AM-Identity.postman_collection.json` or `postman/scripts/*.js`:

```bash
python postman/build_platform_postman.py
python postman/scripts/sync_platform_postman.py   # needs POSTMAN_API_KEY; AM-Platform only
```

Edits to `environment.defaults.json` or `postman/scripts/*.js` are picked up on rebuild.

## Per-service JSON (builder input, not for import)

- `am-identity/postman/`
- `am-subscription/postman/`
- `am-notification/postman/`
