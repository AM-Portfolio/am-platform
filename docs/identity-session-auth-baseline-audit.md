# Identity session auth — Phase 0 baseline audit

Date: 2026-09-03  
Branch: `feature/refresh-token`

## Flutter client (am-modern-ui)

| Check | Result |
|-------|--------|
| `useIdentityAuth` | `true` in `am_design_system/lib/core/config/feature_flags.dart` |
| Refresh URL | `POST /identity/auth/refresh` via `AuthEndpoints.identityRefreshToken` |
| 401 interceptor | Implemented in `am_auth_ui/lib/core/network/auth_interceptor.dart` |
| Logout body | Sends `refresh_token` in POST body |

## Keycloak token issuer audit

| Flow | Client (`azp` / grant) | Session TTL today | Target |
|------|------------------------|-------------------|--------|
| Email/password login | `am-identity-service` | Realm 30m idle / 10h max | Route mobile → platform clients (Phase 2) |
| Refresh | `am-identity-service` | Same | Match issuing client |
| Google web callback | `am-web-client` | Same | 7d client override (Phase 2) |
| Google mobile id_token | `am-identity-service` | Same | 15d mobile override (Phase 2) |

## Keycloak admin session fields

Realm baseline (`automation/terraform/modules/keycloak/main.tf`):

- `sso_session_idle_timeout = 30m`
- `sso_session_max_lifespan = 10h`
- `access_token_lifespan = 5m`
- `revoke_refresh_token` — not set (Phase 2)

Per-client session overrides for `am-web-client`, `am-android-client`, `am-ios-client` — not set (Phase 2).

## Session revoke mapping

| Operation | Keycloak API | am-identity endpoint |
|-----------|--------------|----------------------|
| Single logout | `POST /logout` with refresh token | `POST /auth/logout` |
| Admin revoke session | `DELETE /admin/realms/{realm}/sessions/{id}` | Phase 6 `DELETE /users/me/login-sessions/{id}` |
| Sign out everywhere | Admin user logout | Phase 6 bulk revoke |

## Postman refresh proof (manual)

Collection: `am-identity/postman/AM-Identity.postman_collection.json`

Steps:

1. `POST /auth/login` with test user → save `refresh_token`
2. Wait until access token expires (>5m) or use expired access token on a protected call
3. `POST /auth/refresh` with `refresh_token` → expect 200 + new `access_token`

Preprod script: `am-identity/scripts/verify_preprod_identity.py`

## Phase 0 outcome

Baseline validated in code review. Client refresh (Phase 1) implemented in am-modern-ui. Platform TTL and session APIs tracked in Phases 2–6.
