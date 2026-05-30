# AM Identity — Implementation Plan

## Background
The `am-identity` service replaces the legacy 2-microservice split (`am-auth-tokens` and `am-user-management`). It collapses them into one single Python FastAPI service without backwards-compatible v1 routes.

## Repo Location
`am-platform/am-identity`

## Internal Port
`8113`

`8001` remains reserved for the legacy `am-auth-tokens` local service during migration. External clients should call `am-identity` through Traefik/API Gateway routes under `/api/auth/*` and `/api/users/*`.

## Status
Scaffolding unified Keycloak-backed identity layer with adapter pattern.

## Responsibilities & Features
- **Centralized Authentication:** Manage user login, registration, and logout acting as an adapter over Keycloak.
- **Token Management:** Handle access tokens, refresh tokens, and token validation.
- **Service-to-Service Auth:** Maintain server/service-level auth and machine-to-machine tokens for internal requests.
- **OTP & MFA:** OTP-based login and Multi-Factor Authentication integration.
- **User Settings & Profile:** Expose endpoints for a dedicated frontend user settings page, returning user info, roles, and profile settings using token-based auth.

## API Endpoints

### `api/auth_router.py`
```
POST  /auth/register                   → IIdentityProvider.create_user()
POST  /auth/login                      → IIdentityProvider.authenticate()
POST  /auth/login/otp                  → IIdentityProvider.authenticate_otp()
POST  /auth/refresh                    → IIdentityProvider.refresh_token()
POST  /auth/logout                     → IIdentityProvider.revoke_token()
POST  /auth/password-reset             → IIdentityProvider.request_password_reset()
POST  /auth/password-reset/confirm     → IIdentityProvider.confirm_password_reset()
POST  /auth/google                     → IIdentityProvider.authenticate_google()
```

### `api/user_router.py`
*(Requires valid Access Token for /me routes)*
```
GET   /users/me                        → IIdentityProvider.get_current_user_info() (Returns profile, roles, settings)
PATCH /users/me/settings               → IIdentityProvider.update_user_settings()
GET   /users/{user_id}/status          → IIdentityProvider.get_user_by_id()
PATCH /users/{user_id}/status          → IIdentityProvider.set_user_status()
GET   /users/email/{email}/status
PATCH /users/email/{email}/status
```

### `api/internal.py`
*(For Server/Service-level Auth)*
```
GET   /internal/users/{user_id}
POST  /internal/auth/validate-credentials
POST  /internal/auth/service-token     → Generate Service-to-Service Token
```

## Gateway Route Decisions

Public routes exposed through Traefik/API Gateway:

```
POST  /api/auth/register
POST  /api/auth/login
POST  /api/auth/refresh
POST  /api/auth/logout
POST  /api/auth/password-reset
POST  /api/auth/password-reset/confirm
POST  /api/auth/otp/*
GET   /api/users/me
PATCH /api/users/me/settings
```

Internal routes remain private and are not routed externally:

```
GET   /internal/users/{user_id}
POST  /internal/auth/validate-credentials
POST  /internal/auth/service-token
```

## Token And Claim Contract

Required access-token claims:

- `sub`: Keycloak user ID.
- `email`: verified user email where available.
- `roles`: platform roles mapped from Keycloak roles/groups.
- `tenant_id`: tenant or organization context.
- `org_id`: organization identifier for enterprise users.
- `aud`: expected consumer service or gateway audience.
- `iss`: Keycloak issuer.
- `scope`: granted OAuth scopes.
- `session_id`: login session identifier for audit and logout.
- `token_type`: `user` or `service`.

Service tokens must be short-lived and audience-bound. Internal services must reject tokens where `aud` does not match the target service.

## Migration Cutover Plan

The legacy `am-auth` migration is resolved as a controlled cutover:

1. Inventory current clients, routes, token claims, roles, user IDs, and frontend dependencies.
2. Map legacy users to Keycloak `sub` while preserving stable external user IDs where portfolio, trade, or market records depend on them.
3. Run `am-identity` on internal port `8113` behind non-default gateway routes and compare login/profile responses.
4. Canary selected clients to `/api/auth/*` backed by `am-identity`.
5. Cut over all auth traffic to `am-identity` and freeze legacy user writes.
6. Roll back by restoring the gateway route to legacy auth if smoke tests fail.

Required smoke tests:

- Register, login, refresh, logout.
- Password reset request and confirmation.
- `/users/me` profile and settings retrieval.
- Service token generation and validation.
- Role and entitlement claim propagation to `am-subscription`.
