# API Keys Handoff — am-identity

## Status — 2026-08-02

- API-key persistence, management routes, and token exchange exist locally.
- Repository: `am-platform` on `main`, with the identity changes uncommitted.
- This work must move to a feature branch before any commit.
- Current live blocker: the dev create-key request returned HTTP 404.
- Most likely cause: `am-identity` has not been redeployed with the new routes.

## Goal / architecture

“Call Asrax” AI is `fin-agent`, exposed in dev through:

`https://am-dev.asrax.in/ai` → AI gateway → fin-agent → `am-analysis`

Identity owns API keys and token minting:

1. An authenticated user creates or manages keys through identity.
2. A client exchanges `key_id` plus the one-time secret at `/auth/api-key`.
3. Identity verifies the Argon2id hash and calls `issue_tokens_for_user`.
4. The returned JWT uses `sub` as the authoritative user identity.
5. Clients send that JWT to Call Asrax as `Authorization: Bearer <token>`.

Never send a raw API key to fin-agent as the Authorization credential.

## Git topology

- `AM-Portfolio-grp` is **not** a Git repository; its parent `.git` was removed.
- Work and commit only in nested repositories:
  - `am-platform`
  - `am-agents`
  - `am-modern-ui`
  - `am-gateways`
- Current `am-platform` state is `main...origin/main` plus uncommitted identity WIP.
- Create/switch to a feature branch before committing; preserve all existing WIP.

## Implemented and verified in the tree

### Storage and migration

- `migrations/001_create_api_keys.sql` defines the PostgreSQL `api_keys` table.
- Database: `am_identity`.
- The migration has already been applied on the VPS.
- Startup database initialization also executes the idempotent migration.
- `ApiKeyStore` persists key metadata in PostgreSQL.
- Secrets are hashed with Argon2id and are not stored in plaintext.
- The creation response returns the secret only once.
- `last_used_at` is updated after successful token exchange.
- Revocation records `revoked_at`; revoked keys cannot be used.

### API routes

- `GET /users/me/api-keys` lists the authenticated user's keys.
- `POST /users/me/api-keys` creates a key.
- `DELETE /users/me/api-keys/{record_id}` revokes a key owned by the user.
- `POST /auth/api-key` exchanges `key_id` plus `secret` for normal tokens.
- Management routes derive ownership from authenticated JWT `sub`.
- Exchange calls the identity provider's `issue_tokens_for_user`.
- Exchange is rate-limited (`api-key`, limit 10).
- Invalid key credentials return HTTP 401.
- Missing database configuration returns HTTP 503 for key storage.
- `am_identity/main.py` includes `api_key_router`.

### Vault and deployment configuration

- Identity Vault path: `apps/data/dev/services/am-identity`.
- It contains `DATABASE_URL` and `OIDC_*` values.
- Helm Vault mappings expose `DATABASE_URL` to identity.
- Fin-agent mounts the same identity path and maps `OIDC_ISSUER` and
  `OIDC_JWKS_URL` to `AUTH_ISSUER` and `AUTH_JWKS_URL`.
- Fin-agent `AUTH_REQUIRED` is still `false` pending end-to-end smoke tests.
- Do not print or document actual Vault values.

## Shared environment facts

- Postman workspace: Asrax, ID `648a186b-f56c-4a95-b8ff-9a235cbde152`.
- Collection: **AM Identity Service**.
- Folder: **06 API Keys**.
- Useful environments:
  - **AM Platform - Dev**
  - **AM Fin-Agent - Dev**
- Expected dev management URL:
  `https://am-dev.asrax.in/identity/users/me/api-keys`

## Left / blockers — ordered

1. Protect the local work by creating an `am-platform` feature branch before commit.
2. Review the complete uncommitted diff and run identity tests locally.
3. Build and redeploy `am-identity` to `am-apps-dev`.
4. Confirm the deployed OpenAPI/routes include `/users/me/api-keys` and
   `/auth/api-key`; the observed 404 strongly indicates an old image.
5. In Postman, verify create, list, exchange, and revoke end-to-end.
6. Use the exchanged access token against Call Asrax for a real portfolio summary.
7. Commit/open review from the feature branch; never commit API secrets or JWTs.

## How to continue

1. Inspect and branch without losing WIP:
   `cd a:\InfraCode\AM-Portfolio-grp\am-platform && git status --short --branch`
   then create an appropriately named feature branch.
2. Test/build the identity service, publish the image, and redeploy it to
   `am-apps-dev` using the repository's normal deployment flow.
3. Run collection folder **06 API Keys** with **AM Platform - Dev**:
   create → list → exchange → call AI with Bearer JWT → revoke → reject exchange.

## Suggested endpoint checks

- Management requests require a normal signed-in Bearer JWT.
- Create should return 201 and show the secret exactly once.
- List must not return secret material.
- Exchange should return the same token shape as other identity login flows.
- Successful exchange should update `last_used_at`.
- Revocation should return 204 and prevent future exchange.
- A user must not list or revoke another user's keys.
- Rate limiting should return the service's standard throttling response.

## Success criteria

- Live dev no longer returns 404 for the API-key routes.
- The database connection comes from Vault-backed `DATABASE_URL`.
- API keys only mint tokens; JWT `sub` remains the identity across services.
- Fin-agent receives Bearer JWTs, never raw API keys.
- Create/list/exchange/revoke pass against the deployed service.
- No secrets or pasted JWTs enter source control, docs, or logs.

## Cross-repository handoffs

- Fin-agent: `am-agents/fin-portfolio-agent/docs/HANDOFF_JWT_API_KEYS.md`
- UI: `am-modern-ui/docs/HANDOFF_API_KEYS.md`
- Gateway: `am-gateways/mcp-gateway/`
