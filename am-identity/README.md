# am-identity

Unified identity service for AM Platform.

## Local run

From repo root (`am-platform/`):

```bash
npm run identity:dev
```

Or from this folder:

```bash
npm run dev
```

Loads `.env` / `.secrets.env` from platform root and sets `PYTHONPATH` for shared libraries.

## Main route groups

- `/auth/*` public auth entrypoints (register, login, refresh, logout)
- `/users/me*` authenticated user profile/settings endpoints
- `/internal/*` service-only endpoints

API key routes are additive:

- `GET|POST /users/me/api-keys` and `DELETE /users/me/api-keys/{id}` require a
  normal session Bearer token.
- `POST /auth/api-key` exchanges `key_id` plus `secret` for the normal
  `TokenResponse`. The secret is returned only by the create request.

Set `DATABASE_URL` to a PostgreSQL DSN. Startup applies
`migrations/001_create_api_keys.sql`; without a DSN, existing identity routes
continue to run and API key routes return `503`.

## Postman

Import the collection and environment from [`postman/`](postman/README.md):

- `postman/AM-Identity.postman_collection.json`
- `postman/AM-Identity.local.postman_environment.json`

<!-- dummy trigger commit -->
